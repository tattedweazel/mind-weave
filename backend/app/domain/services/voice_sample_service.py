"""CRUD for user-owned Voice Samples (reference WAV + transcript for voice clone)."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.domain.schemas.voice_samples import VoiceSampleCreate
from app.persistence.tables import TtsModelArtifact, VoiceSample


def _max_voice_sample_bytes() -> int:
    return max(1024, int(settings.TTS_BRIDGE_MAX_AUDIO_BYTES))


class VoiceSampleService:
    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id

    def list_samples(self) -> List[VoiceSample]:
        return list(
            self.session.exec(
                select(VoiceSample).where(VoiceSample.user_id == self.user_id).order_by(VoiceSample.name_lower)
            ).all()
        )

    def get(self, sample_id: uuid.UUID) -> Optional[VoiceSample]:
        return self.session.exec(
            select(VoiceSample).where(VoiceSample.id == sample_id, VoiceSample.user_id == self.user_id)
        ).first()

    def create(self, data: VoiceSampleCreate) -> VoiceSample:
        cap = _max_voice_sample_bytes()
        try:
            raw = base64.b64decode(data.audio_base64.strip(), validate=True)
        except Exception as e:
            raise ValueError("Invalid base64 audio") from e
        if len(raw) > cap:
            raise ValueError(f"Reference audio exceeds maximum size ({cap} bytes)")
        if not raw.startswith(b"RIFF"):
            raise ValueError("Reference audio must be a RIFF/WAV file")

        name_lower = data.name.strip().lower()
        existing = self.session.exec(
            select(VoiceSample).where(VoiceSample.user_id == self.user_id, VoiceSample.name_lower == name_lower)
        ).first()
        if existing:
            raise ValueError("A voice sample with that name already exists")

        if data.design_model_id is not None:
            art = self.session.get(TtsModelArtifact, data.design_model_id)
            if art is None:
                raise ValueError("Unknown design_model_id")

        now = datetime.now(timezone.utc)
        row = VoiceSample(
            user_id=self.user_id,
            name=data.name.strip(),
            name_lower=name_lower,
            ref_text=data.ref_text.strip(),
            ref_audio=raw,
            language=(data.language or "English").strip() or "English",
            instruct=(data.instruct or "").strip(),
            design_model_id=data.design_model_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete(self, sample_id: uuid.UUID) -> bool:
        row = self.get(sample_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.commit()
        return True
