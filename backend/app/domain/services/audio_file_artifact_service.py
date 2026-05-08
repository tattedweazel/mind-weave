"""CRUD for user-owned audio file artifacts used by Audio File Input."""

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlmodel import Session, select

from app.domain.audio_file_validation import ValidatedAudioFile
from app.persistence.tables import AudioFileArtifact, utc_now


class AudioFileArtifactService:
    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id

    def list_artifacts(self) -> List[AudioFileArtifact]:
        # Transient rows (runtime uploads spilled by transcribe_file) are intentionally
        # excluded so they never appear in the artifact picker.
        return list(
            self.session.exec(
                select(AudioFileArtifact)
                .where(
                    AudioFileArtifact.user_id == self.user_id,
                    AudioFileArtifact.transient == False,  # noqa: E712 — SQLAlchemy expression form
                )
                .order_by(AudioFileArtifact.created_at.desc())
            ).all()
        )

    def get(self, artifact_id: uuid.UUID) -> Optional[AudioFileArtifact]:
        return self.session.exec(
            select(AudioFileArtifact).where(
                AudioFileArtifact.id == artifact_id,
                AudioFileArtifact.user_id == self.user_id,
            )
        ).first()

    def create(self, data: bytes, validated: ValidatedAudioFile) -> AudioFileArtifact:
        now = utc_now()
        row = AudioFileArtifact(
            user_id=self.user_id,
            filename=validated.filename,
            mime_type=validated.mime_type,
            size_bytes=validated.size_bytes,
            audio_bytes=data,
            transient=False,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def create_transient(self, data: bytes, validated: ValidatedAudioFile) -> AudioFileArtifact:
        """Spill a runtime audio upload to the artifact table, flagged transient.

        Used by `transcribe_file` so a long-running cloud transcription survives client
        disconnects and process restarts. Transient rows are hidden from the regular
        artifact list and cleaned up after their owning transcription job finalizes.
        """
        now = utc_now()
        row = AudioFileArtifact(
            user_id=self.user_id,
            filename=validated.filename,
            mime_type=validated.mime_type,
            size_bytes=validated.size_bytes,
            audio_bytes=data,
            transient=True,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete(self, artifact_id: uuid.UUID) -> bool:
        row = self.get(artifact_id)
        if row is None:
            return False
        self.session.delete(row)
        self.session.commit()
        return True
