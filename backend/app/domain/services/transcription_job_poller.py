"""Lifespan poller that advances in-flight transcription_jobs rows.

Started by the FastAPI ``lifespan`` (see :mod:`app.main`) and stopped on shutdown. Polls
the `transcription_jobs` table on a fixed cadence and, for each non-terminal row that
isn't a synchronous provider, calls ``provider.poll(...)`` to advance state. Updates the
row + cleans up any transient audio artifact when the job reaches a terminal status.

Concurrency model: single-task / single-worker. For multi-worker deployments a shared
lock is required (documented in ``docs/OPERATIONS.md``); the same caveat already applies
to ``transcribe_pending`` for runtime-upload audio.

The poller does **not** attempt to resume the workflow run. Its only job is to keep the
external transcription itself moving forward so the data survives client disconnects.
A reattach via ``POST /api/v1/workflow-runs/{run_id}/reattach-stream`` exposes the row's
state to the client.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional, Sequence

from sqlmodel import Session

from app.core.config import settings
from app.core.logging import logger
from app.core.user_api_keys_crypto import decrypt_api_keys_store
from app.domain.services.transcription_job_service import (
    TranscriptionJobService,
    list_pending_jobs_for_poller,
)
from app.persistence.db import engine
from app.persistence.tables import TranscriptionJob, User
from app.providers.transcription import (
    SpeechTranscriptionProvider,
    TranscriptionOptions,
    TranscriptionProviderError,
    get_speech_provider,
)
from app.providers.transcription.keys import resolve_assemblyai_api_key


class TranscriptionJobPoller:
    """Background asyncio.Task that advances pending transcription_jobs rows.

    Use :meth:`start` and :meth:`stop` from the FastAPI lifespan; the public surface is
    intentionally tiny (no public methods need to be called from request handlers). The
    poller is safe to start/stop multiple times — duplicate starts are no-ops, and
    ``stop`` is idempotent.
    """

    def __init__(self, *, poll_interval_seconds: Optional[float] = None) -> None:
        cadence = poll_interval_seconds
        if cadence is None:
            cadence = settings.TRANSCRIPTION_JOB_POLL_INTERVAL
        self._poll_interval_seconds = max(0.0, float(cadence))
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event: Optional[asyncio.Event] = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Schedule the poll loop. No-op if already running or cadence is 0."""
        if self.is_running:
            return
        if self._poll_interval_seconds <= 0:
            logger.info("transcription_job_poller disabled (TRANSCRIPTION_JOB_POLL_INTERVAL <= 0)")
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._run_loop(),
            name="transcription_job_poller",
        )
        logger.info(
            "transcription_job_poller started (interval=%.2fs)",
            self._poll_interval_seconds,
        )

    async def stop(self, *, timeout: float = 5.0) -> None:
        """Signal the loop to exit and await its task. Idempotent."""
        if not self.is_running or self._stop_event is None:
            self._task = None
            self._stop_event = None
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=timeout)  # type: ignore[arg-type]
        except asyncio.TimeoutError:
            assert self._task is not None
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        finally:
            self._task = None
            self._stop_event = None
            logger.info("transcription_job_poller stopped")

    async def _run_loop(self) -> None:
        assert self._stop_event is not None
        try:
            while not self._stop_event.is_set():
                try:
                    await self.poll_once()
                except Exception:
                    # Never let a single tick kill the loop. Backoff implicit via sleep.
                    logger.exception("transcription_job_poller tick failed")
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self._poll_interval_seconds,
                    )
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    # Exposed for tests (so they can drive a single tick deterministically).
    async def poll_once(self) -> int:
        """Advance every pending non-terminal job once. Returns the count processed."""
        jobs = self._fetch_pending()
        if not jobs:
            return 0
        processed = 0
        for stub in jobs:
            try:
                await self._advance_one(stub.id)
                processed += 1
            except Exception:
                logger.exception(
                    "transcription_job_poller failed to advance job_id=%s",
                    stub.id,
                )
        return processed

    def _fetch_pending(self) -> Sequence[TranscriptionJob]:
        # New session per fetch so the poller never holds long-lived connections.
        with Session(engine) as session:
            rows = list_pending_jobs_for_poller(session)
            # Detach by re-instantiating lightweight stubs so we can re-open per-row.
            return [
                TranscriptionJob(
                    id=row.id,
                    user_id=row.user_id,
                    run_id=row.run_id,
                    node_id=row.node_id,
                    for_loop_id=row.for_loop_id,
                    for_loop_iteration=row.for_loop_iteration,
                    provider=row.provider,
                    provider_job_id=row.provider_job_id,
                    status=row.status,
                    audio_artifact_id=row.audio_artifact_id,
                    audio_filename=row.audio_filename,
                    audio_mime_type=row.audio_mime_type,
                    audio_size_bytes=row.audio_size_bytes,
                    options_json=dict(row.options_json or {}),
                    transcript_json=row.transcript_json,
                    provider_metadata=dict(row.provider_metadata or {}),
                    provider_error=row.provider_error,
                    submitted_at=row.submitted_at,
                    completed_at=row.completed_at,
                    last_polled_at=row.last_polled_at,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    async def _advance_one(self, job_id: uuid.UUID) -> None:
        with Session(engine) as session:
            row = session.get(TranscriptionJob, job_id)
            if row is None:
                return
            if row.status in {"completed", "error", "cancelled"}:
                return

            try:
                provider = get_speech_provider(row.provider)
            except TranscriptionProviderError as exc:
                _service_for_row(session, row).mark_error(row, str(exc))
                _service_for_row(session, row).cleanup_transient_audio(row)
                return

            api_key = self._resolve_api_key_for(session, row, provider)

            # If the row never made it past 'submitting' (e.g. process crashed during
            # provider.submit), nothing to poll yet. The next executor reattach will
            # handle this branch — we don't try to re-upload audio from the poller in
            # V1 because the bytes live in audio_file_artifacts.transient and the
            # uploader path may be stale.
            if not row.provider_job_id:
                return

            options = _options_from_row(row)

            try:
                poll_result = await provider.poll(
                    provider_job_id=row.provider_job_id,
                    options=options,
                    api_key=api_key,
                )
            except TranscriptionProviderError as exc:
                if exc.retryable:
                    logger.warning(
                        "transcription_job_poller retryable poll error provider=%s job=%s: %s",
                        row.provider,
                        row.provider_job_id,
                        exc,
                    )
                    return
                _service_for_row(session, row).mark_error(row, str(exc))
                _service_for_row(session, row).cleanup_transient_audio(row)
                return
            except Exception:
                logger.exception(
                    "transcription_job_poller unexpected provider error provider=%s job=%s",
                    row.provider,
                    row.provider_job_id,
                )
                return

            updated = _service_for_row(session, row).apply_poll(row, poll_result)
            if updated.status in {"completed", "error", "cancelled"}:
                _service_for_row(session, updated).cleanup_transient_audio(updated)

    def _resolve_api_key_for(
        self,
        session: Session,
        row: TranscriptionJob,
        provider: SpeechTranscriptionProvider,
    ) -> Optional[str]:
        if provider.provider_id != "assemblyai":
            return None
        user = session.get(User, row.user_id)
        if user is None:
            return resolve_assemblyai_api_key(None)
        try:
            decrypted = decrypt_api_keys_store(user.api_keys or {})
        except Exception:
            logger.exception(
                "transcription_job_poller failed to decrypt api_keys for user_id=%s",
                row.user_id,
            )
            decrypted = {}
        return resolve_assemblyai_api_key(decrypted)


def _service_for_row(session: Session, row: TranscriptionJob) -> TranscriptionJobService:
    return TranscriptionJobService(session, row.user_id)


def _normalize_transcription_options_dict(raw: dict[str, Any]) -> dict[str, Any]:
    out = {**raw}
    t = out.get("task")
    if t not in ("transcribe", "translate"):
        out["task"] = "transcribe"
    return out


def _options_from_row(row: TranscriptionJob) -> TranscriptionOptions:
    raw_any: Any = row.options_json or {}
    if not isinstance(raw_any, dict):
        return TranscriptionOptions()
    raw = raw_any
    try:
        return TranscriptionOptions.model_validate(_normalize_transcription_options_dict(raw))
    except Exception:
        return TranscriptionOptions()


# Module-level singleton wired into the FastAPI lifespan.
transcription_job_poller = TranscriptionJobPoller()
