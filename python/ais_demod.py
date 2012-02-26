#!/usr/bin/env python
#ais_demod.py
#implements a hierarchical class to demodulate GMSK packets as per AIS, including differential decoding and bit inversion for NRZI.

from gnuradio import gr, gru, blks2
from gnuradio import eng_notation
#from gnuradio import ais
import gr_ais
from gnuradio import trellis
from gnuradio import window
from gnuradio import digital
import fsm_utils
import gmsk_sync

#from gmskenhanced import gmsk_demod
#from gmskmod import gmsk_demod
import numpy
import scipy
import scipy.stats
import math

#MLSE equalizer using a viterbi decoder on an estimated channel based on a Gaussian matched filter
class va_equalizer(gr.hier_block2):
	def __init__(self, sps, bt):
		gr.hier_block2.__init__(self, "va_equalizer",
                                gr.io_signature(1, 1, gr.sizeof_float), # Input signature
                                gr.io_signature(1, 1, gr.sizeof_char)) # Output signature
		self.modulation = fsm_utils.pam2
		self.channel = list(gr.firdes.gaussian(1, sps, bt, 4))
		self.fsm = trellis.fsm(len(self.modulation[1]), len(self.channel))
		self.tot_channel = fsm_utils.make_isi_lookup(self.modulation, self.channel, True)
		self.dimensionality = self.tot_channel[0]
		self.constellation = self.tot_channel[1]
		if len(self.constellation)/self.dimensionality != self.fsm.O():
			sys.stderr.write ('Incompatible FSM output cardinality and lookup table size.\n')
			sys.exit (1)
		self.metrics = trellis.metrics_f(self.fsm.O(),
										 self.dimensionality,
										 self.constellation,
										 digital.TRELLIS_EUCLIDEAN
										)
		self.va = trellis.viterbi_b(self.fsm, 100000, -1, -1)
		self.connect(self, self.metrics, self.va, self)

class ais_demod(gr.hier_block2):
    def __init__(self, options):

		gr.hier_block2.__init__(self, "ais_demod",
                                gr.io_signature(1, 1, gr.sizeof_gr_complex), # Input signature
                                gr.io_signature(1, 1, gr.sizeof_char)) # Output signature

		self._samples_per_symbol = options.samples_per_symbol
		self._bits_per_sec = options.bits_per_sec
		self._samplerate = self._samples_per_symbol * self._bits_per_sec

		BT = 0.35
		self.filtersections = 16
		self.tapspersection = 30
		self.clockrec_sps = 1

		gain_mu = 0.03

		self.fftlen = options.fftlen
		self.gmsk_sync = gmsk_sync.square_and_fft_sync(self._samplerate, self._bits_per_sec, self.fftlen)
		
		self.datafiltertaps = gr.firdes.gaussian(1, self._samples_per_symbol*self.filtersections, BT, self.tapspersection*self.filtersections)

		self.clockrec = gr.pfb_clock_sync_ccf(self._samples_per_symbol, gain_mu, self.datafiltertaps, self.filtersections, 0, 1.15, self.clockrec_sps)
		
		sensitivity = (math.pi / 2) / self._samples_per_symbol
		self.demod = gr.quadrature_demod_cf(sensitivity) #param is gain
		if(options.viterbi is True):
			self.equalizer = va_equalizer(self.clockrec_sps, BT)
			self.slicer = gr.keep_one_in_n(gr.sizeof_char, self.clockrec_sps)
		else:
			self.equalizer = gr.copy(gr.sizeof_float)
			self.slicer = digital.digital.binary_slicer_fb()

		self.diff = gr.diff_decoder_bb(2)
		self.invert = gr_ais.invert() #NRZI signal diff decoded and inverted should give original signal

		self.connect(self, self.gmsk_sync)
		self.connect(self.gmsk_sync, self.clockrec, self.demod, self.equalizer, self.slicer, self.diff, self.invert, self)


		#debug shit
		#self.demod2=gr.quadrature_demod_cf(sensitivity)
		#self.fsink1 = gr.file_sink(gr.sizeof_float, "demod.dat")
		#self.connect(self.gmsk_sync, self.demod2, self.fsink1)
		#self.fsink2 = gr.file_sink(gr.sizeof_float, "clockrec.dat")
		#self.connect(self.demod, self.fsink2)
		#self.fsink3 = gr.file_sink(gr.sizeof_char, "equal.dat")
		#self.connect(self.equalizer, self.fsink3)
