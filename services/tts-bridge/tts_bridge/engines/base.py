"""TtsEngine protocol."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TtsEngine(Protocol):
    engine_key: str

    def pull(self, artifact_id: str, source: dict[str, Any]) -> str:
        """Download or prepare weights under TTS_MODEL_ROOT; return relative local_key."""

    def synthesize(self, model_local_key: str, text: str, options: dict[str, Any]) -> bytes:
        """Return WAV (or other audio) bytes."""
