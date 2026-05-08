"""Decode path for voice-clone ref audio (base64 may contain ``/`` — not a filesystem path)."""

from __future__ import annotations

import base64
import unittest

from tts_bridge.wav_util import minimal_silent_wav, ref_audio_base64_to_float_wav


class TestRefAudioBase64Decode(unittest.TestCase):
    def test_decode_round_trip(self) -> None:
        wav = minimal_silent_wav(duration_sec=2.0)
        b64 = base64.b64encode(wav).decode("ascii")
        arr, sr = ref_audio_base64_to_float_wav(b64)
        self.assertEqual(sr, 24_000)
        self.assertEqual(arr.ndim, 1)
        self.assertGreater(len(arr), 0)

    def test_rejects_non_wav(self) -> None:
        bad = base64.b64encode(b"not-a-wav").decode("ascii")
        with self.assertRaises(ValueError):
            ref_audio_base64_to_float_wav(bad)


if __name__ == "__main__":
    unittest.main()
