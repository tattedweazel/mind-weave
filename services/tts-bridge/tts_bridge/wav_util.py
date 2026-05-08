"""Minimal WAV helpers (mock / fallback)."""

from __future__ import annotations

import base64
import io
import wave
from typing import Any, Tuple


def minimal_silent_wav(*, duration_sec: float = 0.15, sample_rate: int = 24_000) -> bytes:
    """Short mono PCM16 silence for tests or mock mode."""
    n = max(1, int(sample_rate * duration_sec))
    pcm = b"\x00\x00" * n
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def ref_audio_base64_to_float_wav(b64: str) -> Tuple[Any, int]:
    """Decode **standard base64** RIFF WAV → ``(mono float32 numpy 1-D array, sample_rate)``.

    ``qwen_tts`` accepts ``ref_audio`` as a path, URL, or base64 string, but its base64
    heuristic rejects strings that contain ``/`` (valid in standard base64). Those strings
    are then passed to ``librosa.load`` as a path → **[Errno 63] File name too long**.
    The bridge always decodes here and passes ``(ndarray, sr)`` for the clone path.
    """
    import numpy as np
    import soundfile as sf

    s = (b64 or "").strip()
    if not s:
        raise ValueError("ref_audio_base64 is empty")
    try:
        raw = base64.b64decode(s, validate=False)
    except Exception as e:
        raise ValueError("ref_audio_base64 is not valid base64") from e
    if len(raw) < 12 or not raw.startswith(b"RIFF"):
        raise ValueError("ref_audio_base64 must decode to a RIFF/WAV file")
    with io.BytesIO(raw) as f:
        audio, sr = sf.read(f, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=-1)
    return audio.astype(np.float32), int(sr)


def float_samples_to_wav_bytes(samples: Any, sample_rate: int) -> bytes:
    """Float PCM in [-1, 1] → classic **16-bit PCM RIFF WAV** (stdlib ``wave``).

    Browsers are picky about WAV variants; ``soundfile``/float layouts can play in desktop apps
    but show **0:00** / disabled ``<audio>``. This path matches what ``minimal_silent_wav`` emits.

    ``samples`` may be 1-D (mono) or 2-D *(time × channels)*.
    """
    import numpy as np

    x = np.asarray(samples, dtype=np.float64)
    if x.ndim == 0:
        x = x.reshape(1)
    x = np.nan_to_num(x, nan=0.0, posinf=1.0, neginf=-1.0)
    x = np.clip(x, -1.0, 1.0)
    sr = int(sample_rate)
    if sr < 1:
        raise ValueError("sample_rate must be positive")

    if x.ndim == 1:
        n_channels = 1
        pcm_i16 = (x * 32767.0).astype(np.int16)
        interleaved = pcm_i16
    elif x.ndim == 2:
        n_channels = int(x.shape[1])
        if not 1 <= n_channels <= 16:
            raise ValueError(f"unsupported channel count {n_channels}")
        pcm_i16 = (x * 32767.0).astype(np.int16)
        interleaved = pcm_i16.reshape(-1)
    else:
        raise ValueError(f"unsupported sample dimensions (ndim={x.ndim})")

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(interleaved.tobytes())
    return buf.getvalue()
