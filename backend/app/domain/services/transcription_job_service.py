"""CRUD + lifecycle helpers for the `transcription_jobs` table.

Used by:

* the workflow executor (creates rows on submit, advances state on poll/complete)
* the lifespan poller (`transcription_job_poller`) (advances rows the executor cannot)
* tests + e2e scripts (assert lifecycle correctness)

This module deliberately knows nothing about provider HTTP. Provider calls live in
``app.providers.transcription``; this layer only translates SubmissionResult/PollResult
into row updates.
"""

from __future__ import annotations

import uuid
from typing import Any, Iterable, Optional, Sequence

from sqlmodel import Session, select

from app.domain.audio_file_validation import ValidatedAudioFile
from app.persistence.tables import AudioFileArtifact, TranscriptionJob, utc_now
from app.providers.transcription.base import (
    TERMINAL_JOB_STATUSES,
    PollResult,
    SubmissionResult,
    TranscriptionJobStatus,
    TranscriptionOptions,
)

_NON_TERMINAL_STATUSES: tuple[TranscriptionJobStatus, ...] = (
    "submitting",
    "queued",
    "processing",
)


def normalize_for_loop_id(raw: Any) -> Optional[str]:
    """Match the executor's wait-key normalization so transcription_jobs and pending
    waits agree on identity (None / "" / "0" all collapse to None)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s == "0":
        return None
    return s


def normalize_iteration(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


class TranscriptionJobService:
    """User-scoped helpers for transcription_jobs lifecycle."""

    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id

    # ----- lookup -----

    def get(self, job_id: uuid.UUID) -> Optional[TranscriptionJob]:
        return self.session.exec(
            select(TranscriptionJob).where(
                TranscriptionJob.id == job_id,
                TranscriptionJob.user_id == self.user_id,
            )
        ).first()

    def find_existing_for_node(
        self,
        *,
        run_id: Optional[uuid.UUID],
        node_id: Optional[str],
        for_loop_id: Optional[str],
        for_loop_iteration: Optional[int],
    ) -> Optional[TranscriptionJob]:
        """Look up the active job for an executor (run_id, node_id, loop) tuple.

        Used for idempotency: if the executor restarts mid-job, this finds the row already
        in flight so we resume polling rather than re-submitting.
        """
        stmt = select(TranscriptionJob).where(
            TranscriptionJob.user_id == self.user_id,
            TranscriptionJob.run_id == run_id,
            TranscriptionJob.node_id == node_id,
        )
        rows = self.session.exec(stmt).all()
        norm_loop = normalize_for_loop_id(for_loop_id)
        norm_iter = normalize_iteration(for_loop_iteration)
        for row in rows:
            if normalize_for_loop_id(row.for_loop_id) != norm_loop:
                continue
            if normalize_iteration(row.for_loop_iteration) != norm_iter:
                continue
            return row
        return None

    # ----- creation -----

    def create_pending(
        self,
        *,
        run_id: Optional[uuid.UUID],
        node_id: Optional[str],
        for_loop_id: Optional[str],
        for_loop_iteration: Optional[int],
        provider: str,
        options: TranscriptionOptions,
        audio_artifact_id: Optional[uuid.UUID],
        validated_audio: ValidatedAudioFile,
    ) -> TranscriptionJob:
        """Insert a row in ``submitting`` status before calling provider.submit().

        We persist BEFORE the network call so a crash mid-submit leaves a recoverable
        breadcrumb (the poller / next reattach will requery the provider or surface the
        condition as a clean error).
        """
        now = utc_now()
        row = TranscriptionJob(
            user_id=self.user_id,
            run_id=run_id,
            node_id=node_id,
            for_loop_id=normalize_for_loop_id(for_loop_id),
            for_loop_iteration=normalize_iteration(for_loop_iteration),
            provider=provider,
            provider_job_id=None,
            status="submitting",
            audio_artifact_id=audio_artifact_id,
            audio_filename=validated_audio.filename,
            audio_mime_type=validated_audio.mime_type,
            audio_size_bytes=validated_audio.size_bytes,
            options_json=options.model_dump(mode="json"),
            transcript_json=None,
            provider_metadata={},
            provider_error=None,
            submitted_at=None,
            completed_at=None,
            last_polled_at=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    # ----- updates -----

    def apply_submission(self, row: TranscriptionJob, submission: SubmissionResult) -> TranscriptionJob:
        """Persist the result of provider.submit().

        Synchronous providers return a completed transcript inline; async providers return
        a ``provider_job_id`` and the row stays non-terminal until ``apply_poll`` advances it.
        """
        now = utc_now()
        row.provider_job_id = submission.provider_job_id
        row.status = submission.status
        row.submitted_at = now
        row.last_polled_at = now
        row.updated_at = now
        if submission.provider_metadata:
            merged = dict(row.provider_metadata or {})
            merged.update(submission.provider_metadata)
            row.provider_metadata = merged
        if submission.transcript is not None:
            row.transcript_json = submission.transcript
        if submission.status in TERMINAL_JOB_STATUSES:
            row.completed_at = now
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def apply_poll(self, row: TranscriptionJob, poll: PollResult) -> TranscriptionJob:
        """Persist the result of provider.poll().

        Idempotent on terminal rows — the lifespan poller skips terminal rows, and the
        executor only calls this from its own active loop, but defending against double
        finalization keeps the state machine clean.
        """
        if row.status in TERMINAL_JOB_STATUSES:
            return row
        now = utc_now()
        row.status = poll.status
        row.last_polled_at = now
        row.updated_at = now
        if poll.transcript is not None:
            row.transcript_json = poll.transcript
        if poll.error_message:
            row.provider_error = poll.error_message
        if poll.provider_metadata:
            merged = dict(row.provider_metadata or {})
            merged.update(poll.provider_metadata)
            row.provider_metadata = merged
        if poll.status in TERMINAL_JOB_STATUSES:
            row.completed_at = now
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def mark_error(self, row: TranscriptionJob, message: str) -> TranscriptionJob:
        """Force a row to ``error`` status with a structured message."""
        if row.status in TERMINAL_JOB_STATUSES:
            return row
        now = utc_now()
        row.status = "error"
        row.provider_error = message
        row.last_polled_at = now
        row.updated_at = now
        row.completed_at = now
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def mark_cancelled(self, row: TranscriptionJob) -> TranscriptionJob:
        if row.status in TERMINAL_JOB_STATUSES:
            return row
        now = utc_now()
        row.status = "cancelled"
        row.last_polled_at = now
        row.updated_at = now
        row.completed_at = now
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    # ----- cleanup -----

    def cleanup_transient_audio(self, row: TranscriptionJob) -> bool:
        """Delete the transient audio_file_artifact row associated with a finalized job.

        Idempotent: returns False if there's no transient artifact to delete or the row
        is not yet terminal. Operator-saved (non-transient) artifacts are never touched.
        """
        if row.status not in TERMINAL_JOB_STATUSES:
            return False
        if row.audio_artifact_id is None:
            return False
        artifact = self.session.exec(
            select(AudioFileArtifact).where(
                AudioFileArtifact.id == row.audio_artifact_id,
                AudioFileArtifact.user_id == self.user_id,
                AudioFileArtifact.transient == True,  # noqa: E712
            )
        ).first()
        if artifact is None:
            return False
        self.session.delete(artifact)
        self.session.commit()
        return True


# ----- module-level helpers used by the lifespan poller (no user scoping) -----


def list_pending_jobs_for_poller(session: Session) -> Sequence[TranscriptionJob]:
    """Return non-terminal jobs the lifespan poller should advance.

    Excludes synchronous providers since their rows are created+finalized in one
    transaction by the executor and never linger in a non-terminal state.
    """
    statuses: Iterable[str] = _NON_TERMINAL_STATUSES
    rows = session.exec(
        select(TranscriptionJob).where(
            TranscriptionJob.status.in_(list(statuses)),  # type: ignore[attr-defined]
            TranscriptionJob.provider != "local_whisper",
        )
    ).all()
    return list(rows)
