"""Focused checks for stopping and resuming streamed voice playback."""

import unittest

import numpy as np

from app import AudioPlayback, SpeechDetector, pcm_rms


class InterruptionTests(unittest.TestCase):
    def test_local_speech_clears_queued_and_partial_audio(self):
        playback = AudioPlayback(0)
        playback.enqueue(b"A" * 8)
        self.assertEqual(playback.callback(None, 2, None, None)[0], b"A" * 4)
        playback.enqueue(b"B" * 4)
        playback.set_user_speaking(True)
        self.assertTrue(playback.interrupt())
        self.assertEqual(playback.callback(None, 4, None, None)[0], b"\0" * 8)
        playback.enqueue(b"C" * 4)
        playback.set_user_speaking(False)
        playback.enqueue(b"D" * 4)
        self.assertEqual(playback.callback(None, 2, None, None)[0], b"\0" * 4)
        playback.server_interrupted()
        playback.enqueue(b"E" * 4)
        self.assertEqual(playback.callback(None, 2, None, None)[0], b"E" * 4)

    def test_finished_turn_can_accept_next_reply(self):
        playback = AudioPlayback(0)
        playback.enqueue(b"A" * 8)
        playback.turn_complete()
        playback.set_user_speaking(True)
        self.assertTrue(playback.interrupt())
        playback.set_user_speaking(False)
        playback.enqueue(b"B" * 4)
        self.assertEqual(playback.callback(None, 2, None, None)[0], b"B" * 4)

    def test_speech_detector_requires_sustained_voice(self):
        detector = SpeechDetector()
        self.assertEqual(detector.update(1000), (False, False))
        self.assertEqual(detector.update(100), (False, False))
        self.assertEqual(detector.update(1000), (False, False))
        self.assertEqual(detector.update(1000), (True, False))
        for _ in range(3):
            self.assertEqual(detector.update(100), (False, False))
        self.assertEqual(detector.update(100), (False, True))

    def test_pcm_rms(self):
        self.assertEqual(pcm_rms(np.array([1000, -1000], dtype="<i2").tobytes()), 1000)


if __name__ == "__main__":
    unittest.main()
