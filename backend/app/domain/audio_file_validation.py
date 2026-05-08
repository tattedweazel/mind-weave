"""Validation helpers for user-uploaded audio files used by workflow STT."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath

from app.core.config import settings

SUPPORTED_AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "flac", "webm"}
SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mp4",
    "audio/m4a",
    "audio/aac",
    "audio/ogg",
    "application/ogg",
    "audio/flac",
    "audio/x-flac",
    "audio/webm",
}


class AudioFileValidationError(ValueError):
    """Raised when an uploaded audio file cannot be accepted for transcription."""


@dataclass(frozen=True)
class ValidatedAudioFile:
    filename: str
    mime_type: str
    size_bytes: int


def safe_audio_filename(filename: str | None) -> str:
    name = PurePath((filename or "").replace("\\", "/")).name.strip()
    return name or "audio.webm"


def validate_audio_upload(data: bytes, *, filename: str | None, content_type: str | None) -> ValidatedAudioFile:
    if not data:
        raise AudioFileValidationError("Audio file is empty.")
    if len(data) > settings.STT_MAX_AUDIO_UPLOAD_BYTES:
        raise AudioFileValidationError(f"Audio file exceeds maximum size ({settings.STT_MAX_AUDIO_UPLOAD_BYTES} bytes).")

    safe_name = safe_audio_filename(filename)
    suffix = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    mime = (content_type or "application/octet-stream").split(";", 1)[0].strip().lower() or "application/octet-stream"

    if suffix not in SUPPORTED_AUDIO_EXTENSIONS and mime not in SUPPORTED_AUDIO_MIME_TYPES:
        raise AudioFileValidationError(
            "Unsupported audio format. Please select an MP3, WAV, M4A, OGG, FLAC, or WEBM file."
        )

    return ValidatedAudioFile(filename=safe_name, mime_type=mime, size_bytes=len(data))
