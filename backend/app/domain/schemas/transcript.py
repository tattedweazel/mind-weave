"""Transcript Primitive — normalized speech-to-text artifact shape.

This is the **canonical wire shape** emitted by the provider-abstracted ``transcribe_file``
skill. All transcription providers (``local_whisper``, ``assemblyai``, future cloud
providers) normalize their responses into this structure so downstream workflow nodes
remain provider-agnostic.

The shape is also persisted in ``transcription_jobs.transcript_json`` (as a dict via
``model_dump``) so a job that completes after a client disconnect can be replayed when
the user re-attaches to the run stream.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Bumped only when the wire shape changes in a non-additive way.
TRANSCRIPT_PRIMITIVE_VERSION: int = 1


class TranscriptSegment(BaseModel):
    """A diarization-aware time-bounded text segment.

    Speakers are abstract labels (``A``, ``B``, …). Provider-specific identity (e.g.
    "Speaker 0" or named participants) is **not** carried here — that is a future concern
    per the V1 spec.
    """

    id: str
    speaker: Optional[str] = None
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str


class TranscriptWord(BaseModel):
    """A single word with timing + (optional) speaker + confidence.

    Only populated when the request opts into ``include_word_timestamps`` AND the chosen
    provider's capabilities include ``word_timestamps``. Otherwise the ``words`` list on
    the primitive is empty.
    """

    word: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    speaker: Optional[str] = None
    confidence: Optional[float] = None


class TranscriptMetadata(BaseModel):
    """Provenance and provider extras.

    Provider-specific payloads live under ``provider_metadata`` so debugging and future
    migrations have raw context, but workflow nodes never depend on them.
    """

    model: Optional[str] = None
    diarization_enabled: bool = False
    created_at: datetime
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class TranscriptPrimitive(BaseModel):
    """Normalized transcript artifact emitted by ``transcribe_file``.

    Carried as the ``data`` of a ``DictionaryNodeOutput`` so existing dict-shaped
    consumers (and the output explorer) work without a new node-output kind. The
    ``type`` discriminator lets future logic route on transcripts specifically.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["transcript"] = "transcript"
    version: int = TRANSCRIPT_PRIMITIVE_VERSION
    full_text: str
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    provider: str
    segments: list[TranscriptSegment] = Field(default_factory=list)
    words: list[TranscriptWord] = Field(default_factory=list)
    metadata: TranscriptMetadata


__all__ = [
    "TRANSCRIPT_PRIMITIVE_VERSION",
    "TranscriptMetadata",
    "TranscriptPrimitive",
    "TranscriptSegment",
    "TranscriptWord",
]
