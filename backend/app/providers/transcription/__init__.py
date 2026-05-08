"""Provider-abstracted speech transcription layer.

Workflows never touch provider-specific shapes. All concrete providers normalize
their responses into a single ``TranscriptPrimitive`` (see
``app.domain.schemas.transcript``) so downstream nodes are provider-agnostic.

Adding a new provider:

1. Implement :class:`SpeechTranscriptionProvider` in a new module under this package.
2. Register the class in :mod:`registry`.
3. Add the provider id to ``Settings.TRANSCRIPTION_PROVIDERS_ENABLED`` to expose it in the editor (defaults already list registered V1 providers; override to narrow the list).
"""

from app.providers.transcription.base import (
    PollResult,
    SpeechTranscriptionProvider,
    SubmissionResult,
    TranscriptionJobStatus,
    TranscriptionOptions,
    TranscriptionProviderError,
)
from app.providers.transcription.registry import (
    enabled_provider_ids,
    get_speech_provider,
    list_provider_descriptors,
)

__all__ = [
    "PollResult",
    "SpeechTranscriptionProvider",
    "SubmissionResult",
    "TranscriptionJobStatus",
    "TranscriptionOptions",
    "TranscriptionProviderError",
    "enabled_provider_ids",
    "get_speech_provider",
    "list_provider_descriptors",
]
