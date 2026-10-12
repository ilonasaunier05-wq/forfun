"""Known PCM inputs verify that visual levels reflect audio, including silence."""
import unittest
import numpy as np
from app.audio_levels import pcm_envelope

class AudioLevelTests(unittest.TestCase):
    def test_silence_and_louder_pcm_produce_matching_envelope(self):
        quiet = np.zeros(4800,dtype='<i2').tobytes()
        loud = np.full(4800,8192,dtype='<i2').tobytes()
        self.assertTrue(all(x == 0 for x in pcm_envelope(quiet,48000,-16,1)))
        self.assertTrue(all(abs(x-1) < .001 for x in pcm_envelope(loud,48000,-16,1)))
        quiet_then_loud = pcm_envelope(quiet+loud,48000,-16,1)
        self.assertEqual(quiet_then_loud[:3],[0,0,0])
        self.assertGreater(quiet_then_loud[-1],.99)

    def test_stereo_channels_do_not_cancel_and_unsigned_silence_is_zero(self):
        stereo = np.tile(np.array([8192,-8192],dtype='<i2'),2400).tobytes()
        self.assertGreater(pcm_envelope(stereo,48000,-16,2)[0],.99)
        self.assertEqual(pcm_envelope(bytes([128])*1600,16000,8,1),[0,0,0,0])
