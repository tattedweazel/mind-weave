"""faster-whisper loading and transcription."""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Any

from stt_bridge.config import settings

logger = logging.getLogger(__name__)

_model = None
_model_key: str | None = None


@dataclass
class TranscribeResult:
    text: str
    language: str | None
    segments: list[dict[str, Any]]
    duration_seconds: float | None


def _device_and_compute() -> tuple[str, str]:
    dev = (settings.STT_DEVICE or "auto").strip().lower()
    if dev == "auto":
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                return "cuda", "float16"
        except Exception:
            pass
        return "cpu", "int8"
    if dev in ("cpu", "cuda"):
        ct = (settings.STT_COMPUTE_TYPE or "default").strip()
        if ct == "default":
            return dev, "int8" if dev == "cpu" else "float16"
        return dev, ct
    return "cpu", "int8"


def get_model() -> Any:
    global _model, _model_key
    from faster_whisper import WhisperModel  # heavy import

    key = f"{settings.STT_MODEL}|{_device_and_compute()}"
    if _model is not None and _model_key == key:
        return _model
    device, compute_type = _device_and_compute()
    download_root = str(settings.STT_CACHE_DIR)
    os.makedirs(download_root, exist_ok=True)
    logger.info("Loading faster-whisper model=%s device=%s compute_type=%s", settings.STT_MODEL, device, compute_type)
    _model = WhisperModel(
        settings.STT_MODEL,
        device=device,
        compute_type=compute_type,
        download_root=download_root,
    )
    _model_key = key
    return _model


def transcribe_bytes(
    data: bytes,
    *,
    task: str = "transcribe",
    language: str | None = None,
) -> TranscribeResult:
    """Transcribe audio bytes (any format ffmpeg can read)."""
    if settings.STT_BRIDGE_MOCK:
        return TranscribeResult(
            text="mock transcript",
            language="en",
            segments=[{"start": 0.0, "end": 1.0, "text": "mock transcript"}],
            duration_seconds=1.0,
        )

    model = get_model()
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        return transcribe_path(tmp.name, model=model, task=task, language=language)


def transcribe_path(
    path: str,
    *,
    model: Any = None,
    task: str = "transcribe",
    language: str | None = None,
) -> TranscribeResult:
    m = model or get_model()
    lang = (language or "").strip() or None
    task_clean = (task or "transcribe").strip().lower()
    if task_clean not in ("transcribe", "translate"):
        task_clean = "transcribe"

    segments_out: list[dict[str, Any]] = []
    full_text: list[str] = []
    info_language: str | None = None
    duration: float | None = None

    segments, info = m.transcribe(
        path,
        task=task_clean,
        language=lang,
        vad_filter=True,
    )
    for seg in segments:
        t = seg.text.strip()
        if t:
            full_text.append(t)
        segments_out.append(
            {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text,
            }
        )
    if info and getattr(info, "language", None):
        info_language = str(info.language)
    if info and getattr(info, "duration", None) is not None:
        duration = float(info.duration)

    return TranscribeResult(
        text=" ".join(full_text).strip(),
        language=info_language,
        segments=segments_out,
        duration_seconds=duration,
    )
