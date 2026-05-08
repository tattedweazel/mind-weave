"""Local Whisper transcription provider — thin wrapper around the STT bridge.

Reuses :func:`app.providers.stt_bridge.transcribe_audio_bytes` so existing voice/file
STT behavior is preserved byte-for-byte. The provider is **synchronous** from the
executor's perspective: ``submit()`` returns a completed result in one call, and
``poll()`` is a no-op replay (used only by the lifespan poller for paranoia).

Capabilities are intentionally narrow — segment-level timing is supported by
faster-whisper (and surfaces in the bridge's ``segments`` field), but speaker
diarization and per-word timestamps are not part of the bridge's contract today.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.logging import logger
from app.providers.stt_bridge import SttBridgeError, transcribe_audio_bytes
from app.providers.transcription.base import (
    PollResult,
    SpeechTranscriptionProvider,
    SubmissionResult,
    TranscriptionOptions,
    TranscriptionProviderError,
)

PROVIDER_ID = "local_whisper"


def _build_local_whisper_transcript(
    *,
    bridge_response: dict[str, Any],
    options: TranscriptionOptions,
) -> dict[str, Any]:
    """Normalize the STT bridge response into a TranscriptPrimitive-shaped dict.

    Imported lazily to avoid a Pydantic import on hot paths that don't transcribe.
    """

    from app.domain.schemas.transcript import (
        TRANSCRIPT_PRIMITIVE_VERSION,
        TranscriptMetadata,
        TranscriptPrimitive,
        TranscriptSegment,
    )

    text = str(bridge_response.get("text") or "")
    language = bridge_response.get("language") or options.language
    duration = bridge_response.get("duration_seconds")
    duration_seconds = float(duration) if isinstance(duration, (int, float)) else None
    model = bridge_response.get("model")

    raw_segments = bridge_response.get("segments") or []
    segments: list[TranscriptSegment] = []
    for idx, seg in enumerate(raw_segments):
        if not isinstance(seg, dict):
            continue
        start = seg.get("start") or 0
        end = seg.get("end") or 0
        seg_text = str(seg.get("text") or "")
        try:
            start_ms = max(0, int(round(float(start) * 1000.0)))
            end_ms = max(start_ms, int(round(float(end) * 1000.0)))
        except (TypeError, ValueError):
            continue
        segments.append(
            TranscriptSegment(
                id=f"seg_{idx + 1:04d}",
                speaker=None,  # local Whisper bridge does not diarize today
                start_ms=start_ms,
                end_ms=end_ms,
                text=seg_text,
            ),
        )

    metadata = TranscriptMetadata(
        model=str(model) if isinstance(model, str) else None,
        diarization_enabled=False,
        created_at=datetime.now(tz=timezone.utc),
        provider_metadata={"task": options.task},
    )

    primitive = TranscriptPrimitive(
        type="transcript",
        version=TRANSCRIPT_PRIMITIVE_VERSION,
        full_text=text,
        language=str(language) if isinstance(language, str) else None,
        duration_seconds=duration_seconds,
        provider=PROVIDER_ID,
        segments=segments,
        words=[],
        metadata=metadata,
    )
    return primitive.model_dump(mode="json")


class LocalWhisperProvider(SpeechTranscriptionProvider):
    """Provider backed by ``services/stt-bridge`` (faster-whisper)."""

    provider_id = PROVIDER_ID
    capabilities = frozenset({"timestamps", "translation"})
    is_synchronous = True
    display_name = "Local Whisper (private, on-device)"

    async def submit(
        self,
        *,
        audio: bytes,
        filename: str,
        content_type: str,
        options: TranscriptionOptions,
        api_key: Optional[str],
    ) -> SubmissionResult:
        # api_key is unused — the bridge uses its own optional X-STT-Bridge-Token header.
        del api_key
        try:
            response = await transcribe_audio_bytes(
                audio,
                task=options.task,
                language=options.language,
                filename=filename,
                content_type=content_type,
            )
        except SttBridgeError as exc:
            raise TranscriptionProviderError(
                f"Local Whisper STT bridge failed: {exc}",
                provider_id=PROVIDER_ID,
                retryable=True,
            ) from exc

        try:
            transcript = _build_local_whisper_transcript(bridge_response=response, options=options)
        except Exception as exc:
            logger.exception("local_whisper normalization failed")
            raise TranscriptionProviderError(
                f"Local Whisper normalization failed: {exc}",
                provider_id=PROVIDER_ID,
            ) from exc

        return SubmissionResult(
            provider_job_id=f"lw_{secrets.token_hex(8)}",
            status="completed",
            transcript=transcript,
            provider_metadata={
                "model": response.get("model"),
                "language": response.get("language"),
                "duration_seconds": response.get("duration_seconds"),
            },
        )

    async def poll(
        self,
        *,
        provider_job_id: str,
        options: TranscriptionOptions,
        api_key: Optional[str],
    ) -> PollResult:
        # The local bridge has no async surface; submit returns the final result.
        # The poller never sees `local_whisper` rows (it skips them by provider id),
        # but we implement this for completeness and tests.
        del provider_job_id, options, api_key
        return PollResult(
            status="completed",
            transcript=None,
            provider_metadata={"note": "local_whisper jobs complete inline; poll is a no-op"},
        )

    async def cancel(self, *, provider_job_id: str, api_key: Optional[str]) -> None:
        del provider_job_id, api_key
        # No remote job exists to cancel.
        return None
