"""Speech transcription provider directory.

The editor reads this to populate the provider dropdown on the ``transcribe_file`` skill.
The deployment-wide allow-list lives in ``settings.TRANSCRIPTION_PROVIDERS_ENABLED``;
admins control which providers are advertised to authors.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.persistence.tables import User
from app.providers.transcription import list_provider_descriptors

router = APIRouter()


_PROVIDER_NOTES: dict[str, str] = {
    "local_whisper": (
        "Runs on the bundled stt-bridge sidecar. Audio never leaves your server. "
        "Synchronous; accuracy depends on the loaded Whisper model size."
    ),
    "assemblyai": (
        "Cloud transcription via AssemblyAI (https://assemblyai.com). Audio is uploaded "
        "over HTTPS and processed asynchronously; the workflow run keeps polling and "
        "survives client disconnects via the persisted transcription poller."
    ),
}

_API_KEY_FIELDS: dict[str, str] = {
    "assemblyai": "assemblyai",
}


class TranscriptionModelItem(BaseModel):
    """One speech model exposed for a provider in the workflow editor."""

    id: str
    label: str
    description: Optional[str] = None
    is_default: bool = False


class TranscriptionProviderItem(BaseModel):
    """Editor-facing descriptor; flat shape consumed by the SPA inspector dropdown."""

    id: str
    label: str
    capabilities: List[str]
    is_synchronous: bool
    requires_api_key: bool
    api_key_field: Optional[str] = None
    notes: Optional[str] = None
    models: List[TranscriptionModelItem] = Field(default_factory=list)


@router.get("/transcription/providers", response_model=List[TranscriptionProviderItem])
def get_transcription_providers(
    _current_user: User = Depends(get_current_user),
) -> List[TranscriptionProviderItem]:
    """Return the providers the editor should expose for ``transcribe_file``."""
    return [
        TranscriptionProviderItem(
            id=d.provider_id,
            label=d.display_name,
            capabilities=list(d.capabilities),
            is_synchronous=d.is_synchronous,
            requires_api_key=d.requires_api_key,
            api_key_field=_API_KEY_FIELDS.get(d.provider_id),
            notes=_PROVIDER_NOTES.get(d.provider_id),
            models=[
                TranscriptionModelItem(
                    id=m.id,
                    label=m.label,
                    description=m.description,
                    is_default=m.is_default,
                )
                for m in d.models
            ],
        )
        for d in list_provider_descriptors()
    ]
