"""Base abstractions for speech transcription providers.

Mirrors the ``ModelProvider`` ABC pattern in :mod:`app.providers.base`: a small async
interface plus typed result models. Concrete implementations live alongside this module
and normalize their responses into ``TranscriptPrimitive`` (the workflow-visible shape).

The ABC is uniform across synchronous providers (``local_whisper``, where ``submit``
returns a completed job in one shot) and asynchronous cloud providers (``assemblyai``,
where ``submit`` returns immediately and ``poll`` advances state). The executor and the
lifespan poller drive the same interface either way.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Status vocabulary persisted in `transcription_jobs.status` and surfaced in events/details.
TranscriptionJobStatus = Literal[
    "submitting",
    "queued",
    "processing",
    "completed",
    "error",
    "cancelled",
]

TERMINAL_JOB_STATUSES: frozenset[TranscriptionJobStatus] = frozenset(
    {"completed", "error", "cancelled"},
)


class TranscriptionProviderError(Exception):
    """Raised when a provider call fails or normalization cannot complete.

    The executor maps this to a structured ``transcribe_error`` in node details and the
    persisted ``transcription_jobs.provider_error`` column. No partial transcript is ever
    surfaced to downstream nodes (per spec).
    """

    def __init__(self, message: str, *, provider_id: str | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.provider_id = provider_id
        self.retryable = retryable


@dataclass(frozen=True)
class TranscriptionModelDescriptor:
    """One selectable speech model for a provider (editor + ``TranscriptionOptions``)."""

    id: str
    label: str
    description: Optional[str] = None
    is_default: bool = False


class TranscriptionOptions(BaseModel):
    """Provider-agnostic transcription options resolved from skill ``data`` fields.

    Providers receive this struct verbatim; unsupported options are accepted but silently
    ignored by providers that lack the capability (introspect via ``capabilities``).
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    language: Optional[str] = None
    diarization_enabled: bool = False
    include_word_timestamps: bool = False
    prompt: Optional[str] = None
    task: Literal["transcribe", "translate"] = "transcribe"
    provider_model_id: Optional[str] = Field(
        default=None,
        description="Primary model slug for the chosen provider (e.g. AssemblyAI universal-3-pro).",
    )


@dataclass(frozen=True)
class SubmissionResult:
    """Returned by :meth:`SpeechTranscriptionProvider.submit`.

    For synchronous providers (``local_whisper``), ``status`` will be ``completed`` and
    ``transcript`` will be populated. The executor short-circuits the poll loop in that case.

    For asynchronous providers (``assemblyai``), ``status`` is typically ``queued`` or
    ``processing`` and the executor proceeds to poll using ``provider_job_id``.
    """

    provider_job_id: str
    status: TranscriptionJobStatus
    transcript: Optional[dict[str, Any]] = None  # serialized TranscriptPrimitive when status==completed
    provider_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PollResult:
    """Returned by :meth:`SpeechTranscriptionProvider.poll`."""

    status: TranscriptionJobStatus
    transcript: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)


class SpeechTranscriptionProvider(ABC):
    """Abstract interface for any speech-to-text provider.

    Subclasses MUST set :attr:`provider_id` (used as the manifest/dropdown value) and may
    advertise :attr:`capabilities` (used by the inspector to enable/disable toggles).
    """

    provider_id: ClassVar[str]
    capabilities: ClassVar[frozenset[str]] = frozenset()  # e.g. {"diarization", "word_timestamps", "translation"}
    is_synchronous: ClassVar[bool] = False
    """When True the provider returns a completed transcript from ``submit`` and ``poll`` is a no-op replay."""

    display_name: ClassVar[str] = ""
    """Human-readable label surfaced via ``GET /api/v1/transcription/providers``."""

    model_descriptors: ClassVar[tuple[TranscriptionModelDescriptor, ...]] = ()
    """Speech models this provider exposes in the editor; empty means no per-node model picker."""

    @abstractmethod
    async def submit(
        self,
        *,
        audio: bytes,
        filename: str,
        content_type: str,
        options: TranscriptionOptions,
        api_key: Optional[str],
    ) -> SubmissionResult:
        """Submit audio for transcription. Idempotency is the caller's responsibility.

        ``api_key`` is the resolved Bearer token (or ``None`` for providers that do not
        require one, e.g. the local STT bridge). Providers MUST NOT log the key.
        """

    @abstractmethod
    async def poll(
        self,
        *,
        provider_job_id: str,
        options: TranscriptionOptions,
        api_key: Optional[str],
    ) -> PollResult:
        """Return the latest job status. ``transcript`` is populated only on ``completed``."""

    @abstractmethod
    async def cancel(self, *, provider_job_id: str, api_key: Optional[str]) -> None:
        """Best-effort cancellation. Providers without server-side cancel may no-op."""


@dataclass(frozen=True)
class ProviderDescriptor:
    """Public-facing provider metadata returned by ``GET /api/v1/transcription/providers``."""

    provider_id: str
    display_name: str
    capabilities: list[str]
    is_synchronous: bool
    requires_api_key: bool
    models: tuple[TranscriptionModelDescriptor, ...] = ()
