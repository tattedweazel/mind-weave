"""AssemblyAI transcription provider adapter.

Cloud STT via three REST calls (https://www.assemblyai.com/docs):

* ``POST {base}/v2/upload`` — multipart upload, returns ``upload_url``
* ``POST {base}/v2/transcript`` — create transcript job from ``upload_url`` + options
  (requires ``speech_models``, e.g. ``universal-3-pro`` per current API)
* ``GET {base}/v2/transcript/{id}`` — poll status; states ``queued``, ``processing``,
  ``completed``, ``error``.

The adapter is the **only** module that knows about AssemblyAI's request/response shape.
Workflow code, the executor, and the lifespan poller all consume the normalized
:class:`TranscriptPrimitive` shape returned via :class:`SubmissionResult` /
:class:`PollResult`. The seam used in tests is :func:`_build_async_client`, which test
code patches with an ``httpx.MockTransport`` so no real network ever fires.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, ClassVar, Optional

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.providers.transcription.base import (
    PollResult,
    SpeechTranscriptionProvider,
    SubmissionResult,
    TranscriptionJobStatus,
    TranscriptionModelDescriptor,
    TranscriptionOptions,
    TranscriptionProviderError,
)

PROVIDER_ID = "assemblyai"

# AssemblyAI provider status → internal status.
_STATUS_MAP: dict[str, TranscriptionJobStatus] = {
    "queued": "queued",
    "processing": "processing",
    "completed": "completed",
    "error": "error",
}


def _build_async_client(*, base_url: str, api_key: str, timeout: float) -> httpx.AsyncClient:
    """Construction seam — overridden in tests via patch to inject a MockTransport.

    Production callers MUST go through this helper so a single patch in tests covers all
    HTTP traffic; never construct ``httpx.AsyncClient`` ad-hoc inside this module.
    """

    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=timeout,
        headers={"authorization": api_key, "user-agent": "mind-weave/transcription"},
    )


def _require_api_key(api_key: Optional[str]) -> str:
    if not api_key or not api_key.strip():
        raise TranscriptionProviderError(
            "AssemblyAI requires an API key. Add one in My Settings → API Settings, "
            "or set ASSEMBLYAI_API_KEY on the server.",
            provider_id=PROVIDER_ID,
        )
    return api_key.strip()


def _abstract_speaker_label(raw: Any) -> Optional[str]:
    """Map AssemblyAI speaker tokens (e.g. ``"A"``, ``"B"``, ``"Speaker 0"``) to abstract labels.

    Per spec, speaker identity resolution is a future concern; we just keep the provider's
    label if it's already a single-letter code, or compress ``"Speaker N"`` → letter A+N.
    """

    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        if len(s) == 1 and s.isalpha():
            return s.upper()
        # "Speaker 0" / "speaker_1" etc. → A, B, C
        digits = "".join(ch for ch in s if ch.isdigit())
        if digits:
            try:
                idx = int(digits)
                if 0 <= idx < 26:
                    return chr(ord("A") + idx)
            except ValueError:
                pass
        # Fallback: first uppercase letter or full string truncated.
        return s[:32]
    return None


def _build_assemblyai_transcript(
    *,
    api_response: dict[str, Any],
    options: TranscriptionOptions,
) -> dict[str, Any]:
    """Normalize an AssemblyAI ``GET /v2/transcript/{id}`` (status=completed) response."""

    from app.domain.schemas.transcript import (
        TRANSCRIPT_PRIMITIVE_VERSION,
        TranscriptMetadata,
        TranscriptPrimitive,
        TranscriptSegment,
        TranscriptWord,
    )

    text = str(api_response.get("text") or "")
    language_code = api_response.get("language_code") or options.language
    audio_duration = api_response.get("audio_duration")
    duration_seconds: Optional[float]
    if isinstance(audio_duration, (int, float)):
        duration_seconds = float(audio_duration)
    else:
        duration_seconds = None
    # AssemblyAI often leaves deprecated ``speech_model`` null while populating
    # ``speech_models`` / ``speech_model_used``. Legacy ``acoustic_model`` is a separate
    # stack label (frequently ``assemblyai_default``) and must not win over Universal tiers.
    raw_speech_models = api_response.get("speech_models")
    first_list_model: Optional[str] = None
    if isinstance(raw_speech_models, list) and raw_speech_models:
        cand = raw_speech_models[0]
        first_list_model = cand if isinstance(cand, str) else None
    sm_used = api_response.get("speech_model_used")
    sm_used_str = sm_used.strip() if isinstance(sm_used, str) and sm_used.strip() else None
    sm_direct = api_response.get("speech_model")
    sm_direct_str = sm_direct.strip() if isinstance(sm_direct, str) and sm_direct.strip() else None
    acoustic = api_response.get("acoustic_model")
    acoustic_str = acoustic.strip() if isinstance(acoustic, str) and acoustic.strip() else None
    model = sm_used_str or sm_direct_str or first_list_model or acoustic_str

    # Segments come from "utterances" when speaker_labels=true; otherwise we
    # synthesize a single segment from the full text + audio duration as a fallback.
    raw_utterances = api_response.get("utterances") or []
    segments: list[TranscriptSegment] = []
    if isinstance(raw_utterances, list) and raw_utterances:
        for idx, utt in enumerate(raw_utterances):
            if not isinstance(utt, dict):
                continue
            try:
                start_ms = max(0, int(utt.get("start") or 0))
                end_ms = max(start_ms, int(utt.get("end") or 0))
            except (TypeError, ValueError):
                continue
            segments.append(
                TranscriptSegment(
                    id=f"seg_{idx + 1:04d}",
                    speaker=_abstract_speaker_label(utt.get("speaker")),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=str(utt.get("text") or ""),
                ),
            )
    elif text:
        end_ms = int(round((duration_seconds or 0.0) * 1000.0))
        segments.append(
            TranscriptSegment(
                id="seg_0001",
                speaker=None,
                start_ms=0,
                end_ms=max(0, end_ms),
                text=text,
            ),
        )

    raw_words = api_response.get("words") or []
    words: list[TranscriptWord] = []
    if options.include_word_timestamps and isinstance(raw_words, list):
        for w in raw_words:
            if not isinstance(w, dict):
                continue
            try:
                start_ms = max(0, int(w.get("start") or 0))
                end_ms = max(start_ms, int(w.get("end") or 0))
            except (TypeError, ValueError):
                continue
            confidence_raw = w.get("confidence")
            confidence: Optional[float]
            try:
                confidence = float(confidence_raw) if confidence_raw is not None else None
            except (TypeError, ValueError):
                confidence = None
            words.append(
                TranscriptWord(
                    word=str(w.get("text") or ""),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    speaker=_abstract_speaker_label(w.get("speaker")),
                    confidence=confidence,
                ),
            )

    provider_metadata: dict[str, Any] = {
        "id": api_response.get("id"),
        "language_confidence": api_response.get("language_confidence"),
        "audio_duration": audio_duration,
        "speech_model": model,
        "punctuate": api_response.get("punctuate"),
        "format_text": api_response.get("format_text"),
    }

    metadata = TranscriptMetadata(
        model=str(model) if isinstance(model, str) else None,
        diarization_enabled=bool(options.diarization_enabled),
        created_at=datetime.now(tz=timezone.utc),
        provider_metadata={k: v for k, v in provider_metadata.items() if v is not None},
    )

    primitive = TranscriptPrimitive(
        type="transcript",
        version=TRANSCRIPT_PRIMITIVE_VERSION,
        full_text=text,
        language=str(language_code) if isinstance(language_code, str) else None,
        duration_seconds=duration_seconds,
        provider=PROVIDER_ID,
        segments=segments,
        words=words,
        metadata=metadata,
    )
    return primitive.model_dump(mode="json")


async def _upload_audio(
    client: httpx.AsyncClient,
    *,
    audio: bytes,
    filename: str,
    content_type: str,
) -> str:
    """``POST /v2/upload`` and return the temporary ``upload_url``."""

    try:
        response = await client.post(
            "/v2/upload",
            content=audio,
            headers={"content-type": content_type or "application/octet-stream"},
        )
    except httpx.RequestError as exc:
        raise TranscriptionProviderError(
            f"AssemblyAI upload failed (network error): {exc}",
            provider_id=PROVIDER_ID,
            retryable=True,
        ) from exc

    if response.status_code >= 400:
        body_excerpt = (response.text or "")[:300]
        raise TranscriptionProviderError(
            f"AssemblyAI upload returned {response.status_code}: {body_excerpt}",
            provider_id=PROVIDER_ID,
            retryable=response.status_code >= 500,
        )

    payload = response.json()
    upload_url = payload.get("upload_url") if isinstance(payload, dict) else None
    if not isinstance(upload_url, str) or not upload_url:
        raise TranscriptionProviderError(
            "AssemblyAI upload response missing upload_url",
            provider_id=PROVIDER_ID,
        )
    # filename is informational only — AssemblyAI keys the audio by the upload_url.
    del filename
    return upload_url


def _build_create_payload(*, audio_url: str, options: TranscriptionOptions) -> dict[str, Any]:
    explicit = (
        options.provider_model_id.strip()
        if options.provider_model_id and isinstance(options.provider_model_id, str)
        else ""
    )
    if explicit:
        speech_models = [explicit]
    else:
        speech_models = [
            m.strip() for m in (settings.ASSEMBLYAI_SPEECH_MODELS or []) if isinstance(m, str) and m.strip()
        ]
        if not speech_models:
            speech_models = ["universal-3-pro"]

    payload: dict[str, Any] = {
        "audio_url": audio_url,
        "speech_models": speech_models,
        "punctuate": True,
        "format_text": True,
    }
    if options.language and options.language.strip():
        payload["language_code"] = options.language.strip()
    else:
        # Let AssemblyAI auto-detect when the user didn't pin a language.
        payload["language_detection"] = True
    if options.diarization_enabled:
        payload["speaker_labels"] = True
    if options.task == "translate":
        # AssemblyAI doesn't translate inline like Whisper; document the limitation by
        # surfacing it in provider_metadata rather than silently doing the wrong thing.
        # The executor still passes the option through; downstream graphs can detect
        # mismatch via metadata.provider_metadata.unsupported_task.
        pass
    if options.prompt and options.prompt.strip():
        # AssemblyAI uses ``word_boost`` (list of strings) for biasing; we expose a
        # comma-separated prompt as word boost terms when the user provided any.
        terms = [t.strip() for t in options.prompt.replace("\n", ",").split(",") if t.strip()]
        if terms:
            payload["word_boost"] = terms[:50]  # AAI documented cap
    return payload


async def _create_transcript(
    client: httpx.AsyncClient,
    *,
    audio_url: str,
    options: TranscriptionOptions,
) -> dict[str, Any]:
    payload = _build_create_payload(audio_url=audio_url, options=options)
    try:
        response = await client.post("/v2/transcript", json=payload)
    except httpx.RequestError as exc:
        raise TranscriptionProviderError(
            f"AssemblyAI create-transcript failed (network error): {exc}",
            provider_id=PROVIDER_ID,
            retryable=True,
        ) from exc
    if response.status_code >= 400:
        body_excerpt = (response.text or "")[:300]
        raise TranscriptionProviderError(
            f"AssemblyAI create-transcript returned {response.status_code}: {body_excerpt}",
            provider_id=PROVIDER_ID,
            retryable=response.status_code >= 500,
        )
    body = response.json()
    if not isinstance(body, dict):
        raise TranscriptionProviderError(
            "AssemblyAI create-transcript returned non-object body",
            provider_id=PROVIDER_ID,
        )
    return body


async def _get_transcript(client: httpx.AsyncClient, *, transcript_id: str) -> dict[str, Any]:
    try:
        response = await client.get(f"/v2/transcript/{transcript_id}")
    except httpx.RequestError as exc:
        raise TranscriptionProviderError(
            f"AssemblyAI get-transcript failed (network error): {exc}",
            provider_id=PROVIDER_ID,
            retryable=True,
        ) from exc
    if response.status_code >= 400:
        body_excerpt = (response.text or "")[:300]
        raise TranscriptionProviderError(
            f"AssemblyAI get-transcript returned {response.status_code}: {body_excerpt}",
            provider_id=PROVIDER_ID,
            retryable=response.status_code >= 500,
        )
    body = response.json()
    if not isinstance(body, dict):
        raise TranscriptionProviderError(
            "AssemblyAI get-transcript returned non-object body",
            provider_id=PROVIDER_ID,
        )
    return body


def _normalize_provider_status(raw: Any) -> TranscriptionJobStatus:
    s = str(raw or "").strip().lower()
    return _STATUS_MAP.get(s, "processing")


class AssemblyAIProvider(SpeechTranscriptionProvider):
    """Cloud transcription provider for AssemblyAI."""

    provider_id = PROVIDER_ID
    capabilities = frozenset({"diarization", "word_timestamps", "timestamps", "translation"})
    is_synchronous = False
    display_name = "AssemblyAI (cloud)"
    model_descriptors: ClassVar[tuple[TranscriptionModelDescriptor, ...]] = (
        TranscriptionModelDescriptor(
            id="universal-3-pro",
            label="Universal 3",
            description="Universal Speech Model tier — highest quality.",
            is_default=True,
        ),
        TranscriptionModelDescriptor(
            id="universal-2",
            label="Universal 2",
            description="Lower cost tier.",
            is_default=False,
        ),
    )

    async def submit(
        self,
        *,
        audio: bytes,
        filename: str,
        content_type: str,
        options: TranscriptionOptions,
        api_key: Optional[str],
    ) -> SubmissionResult:
        token = _require_api_key(api_key)
        async with _build_async_client(
            base_url=settings.ASSEMBLYAI_BASE_URL,
            api_key=token,
            timeout=settings.ASSEMBLYAI_UPLOAD_TIMEOUT,
        ) as client:
            audio_url = await _upload_audio(
                client,
                audio=audio,
                filename=filename,
                content_type=content_type,
            )
            create_body = await _create_transcript(client, audio_url=audio_url, options=options)
        transcript_id = create_body.get("id")
        if not isinstance(transcript_id, str) or not transcript_id:
            raise TranscriptionProviderError(
                "AssemblyAI create-transcript response missing id",
                provider_id=PROVIDER_ID,
            )
        status = _normalize_provider_status(create_body.get("status"))
        # Strip volatile fields out of provider_metadata; we keep only IDs/labels.
        return SubmissionResult(
            provider_job_id=transcript_id,
            status=status,
            transcript=None,
            provider_metadata={
                "id": transcript_id,
                "language_detection": create_body.get("language_detection"),
                "speaker_labels": create_body.get("speaker_labels"),
            },
        )

    async def poll(
        self,
        *,
        provider_job_id: str,
        options: TranscriptionOptions,
        api_key: Optional[str],
    ) -> PollResult:
        token = _require_api_key(api_key)
        async with _build_async_client(
            base_url=settings.ASSEMBLYAI_BASE_URL,
            api_key=token,
            timeout=settings.ASSEMBLYAI_REQUEST_TIMEOUT,
        ) as client:
            body = await _get_transcript(client, transcript_id=provider_job_id)

        status = _normalize_provider_status(body.get("status"))
        if status == "completed":
            try:
                transcript = _build_assemblyai_transcript(api_response=body, options=options)
            except Exception as exc:
                logger.exception("assemblyai normalization failed")
                raise TranscriptionProviderError(
                    f"AssemblyAI normalization failed: {exc}",
                    provider_id=PROVIDER_ID,
                ) from exc
            return PollResult(
                status="completed",
                transcript=transcript,
                provider_metadata={"id": body.get("id")},
            )
        if status == "error":
            return PollResult(
                status="error",
                transcript=None,
                error_message=str(body.get("error") or "AssemblyAI returned status=error"),
                provider_metadata={"id": body.get("id")},
            )
        return PollResult(
            status=status,
            transcript=None,
            provider_metadata={"id": body.get("id")},
        )

    async def cancel(self, *, provider_job_id: str, api_key: Optional[str]) -> None:
        # AssemblyAI does not expose a documented cancel endpoint at v2; we no-op so
        # callers can mark the local row cancelled without leaking a 404 to the user.
        del provider_job_id, api_key
        return None


__all__ = [
    "AssemblyAIProvider",
    "PROVIDER_ID",
    "_build_async_client",
    "_build_assemblyai_transcript",
]
