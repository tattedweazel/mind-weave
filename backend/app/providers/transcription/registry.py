"""Speech transcription provider registry.

Single source of truth that maps provider id strings (used in workflow JSON, the editor
dropdown, and persisted ``transcription_jobs.provider``) to concrete adapters.

To add a new provider, instantiate it once here and append the descriptor below. The
``GET /api/v1/transcription/providers`` endpoint intersects ``TRANSCRIPTION_PROVIDERS_ENABLED``
with registered providers so operators can hide options (e.g. cloud-only installs); the
default lists both V1 providers.
"""

from __future__ import annotations

from typing import Mapping

from app.core.config import settings
from app.providers.transcription.assemblyai import AssemblyAIProvider
from app.providers.transcription.base import (
    ProviderDescriptor,
    SpeechTranscriptionProvider,
    TranscriptionProviderError,
)
from app.providers.transcription.local_whisper import LocalWhisperProvider

# Instantiated once per process; providers are stateless so this is safe.
_PROVIDERS: Mapping[str, SpeechTranscriptionProvider] = {
    LocalWhisperProvider.provider_id: LocalWhisperProvider(),
    AssemblyAIProvider.provider_id: AssemblyAIProvider(),
}

# Providers that require a per-user API key (My Settings → API Settings) before use.
_REQUIRES_API_KEY: frozenset[str] = frozenset({AssemblyAIProvider.provider_id})


def get_speech_provider(provider_id: str) -> SpeechTranscriptionProvider:
    """Return the registered provider for ``provider_id`` or raise ``TranscriptionProviderError``.

    The error is intentionally provider-agnostic so unknown ids in stale workflow JSON
    surface the same way regardless of which provider the user attempted.
    """

    pid = (provider_id or "").strip().lower()
    impl = _PROVIDERS.get(pid)
    if impl is None:
        raise TranscriptionProviderError(
            f"Unknown speech transcription provider: {provider_id!r}",
            provider_id=pid or None,
        )
    return impl


def enabled_provider_ids() -> list[str]:
    """Return the subset of registered providers that the deployment has opted into.

    The order is preserved from ``TRANSCRIPTION_PROVIDERS_ENABLED`` so the editor's
    dropdown shows them in operator-defined order. Unknown ids in the env var are
    silently ignored to keep the editor functional during config typos.
    """

    out: list[str] = []
    seen: set[str] = set()
    for raw in settings.TRANSCRIPTION_PROVIDERS_ENABLED or []:
        pid = (raw or "").strip().lower()
        if pid and pid in _PROVIDERS and pid not in seen:
            out.append(pid)
            seen.add(pid)
    return out


def list_provider_descriptors() -> list[ProviderDescriptor]:
    """Materialize public descriptors for the enabled providers (UI dropdown payload)."""

    descriptors: list[ProviderDescriptor] = []
    for pid in enabled_provider_ids():
        impl = _PROVIDERS[pid]
        descriptors.append(
            ProviderDescriptor(
                provider_id=impl.provider_id,
                display_name=impl.display_name or impl.provider_id,
                capabilities=sorted(impl.capabilities),
                is_synchronous=impl.is_synchronous,
                requires_api_key=impl.provider_id in _REQUIRES_API_KEY,
                models=tuple(type(impl).model_descriptors),
            ),
        )
    return descriptors


__all__ = [
    "enabled_provider_ids",
    "get_speech_provider",
    "list_provider_descriptors",
]
