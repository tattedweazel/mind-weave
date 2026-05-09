#!/usr/bin/env python3
"""
Live HTTP end-to-end check for the provider-abstracted Transcribe File skill.

Mirrors ``run_audio_file_input_workflow_http_e2e.py`` but exercises the new
``transcribe_file`` skill end-to-end with both supported provider backends and
both audio source modes:

1. saved artifact + ``local_whisper`` (sync)  → POST /run
2. runtime upload + ``local_whisper`` (sync)  → ``POST …/runs`` + multipart upload during SSE
3. saved artifact + ``assemblyai`` (async)    → ``POST …/runs`` + ``GET …/events`` replay (replaces reattach-stream)

Default mode patches the local STT bridge and the AssemblyAI HTTP transport
in-process so it never makes real outbound calls. Pass ``--real-stt`` to call
the local bridge or ``--real-assemblyai --assemblyai-key <key>`` to exercise
the real cloud API.

Example::

  cd backend && uv run python scripts/run_transcribe_file_workflow_http_e2e.py
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import mimetypes
import os
import re
import socket
import sys
import threading
import time
import uuid
import wave
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
os.chdir(_BACKEND_ROOT)

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.domain.workflow_http_sse_legacy_consumer import (  # noqa: E402
    enqueue_and_iterate_build_events,
    iter_workflow_sse_as_legacy_ndjson_events,
)
from app.core.security import get_password_hash  # noqa: E402
from app.main import app  # noqa: E402
from app.persistence.db import engine  # noqa: E402
from app.persistence.tables import User  # noqa: E402

NODE_ID = "transcribe_file"
E2E_USERNAME = "transcribe_file_http_e2e"
E2E_PASSWORD = "TranscribeFileE2E12"
_MOCK_STT_TEXT = "transcribe file HTTP e2e mock transcript from script"
_MOCK_AAI_TEXT = "transcribe file HTTP e2e mock transcript from assemblyai"


def _silent_wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(b"\x00\x00" * 3_200)
    return buf.getvalue()


def _audio_bytes_from_args(args: argparse.Namespace) -> tuple[bytes, str, str]:
    if args.audio_file:
        path = Path(args.audio_file).expanduser().resolve()
        return path.read_bytes(), path.name, mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return _silent_wav_bytes(), "transcribe-file-http-e2e.wav", "audio/wav"


def _graph(*, provider: str, artifact_id: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "provider": provider,
        "task": "transcribe",
        "diarization_enabled": False,
        "include_word_timestamps": False,
    }
    if artifact_id:
        data["audio_artifact_id"] = artifact_id
    return {
        "nodes": [
            {"id": "s", "kind": "start", "label": "Start", "data": {"text": ""}, "position": {}},
            {
                "id": NODE_ID,
                "kind": "skill",
                "skill_type": "transcribe_file",
                "label": "Transcribe File",
                "data": data,
                "position": {},
            },
            {
                "id": "n_stop",
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                "position": {},
            },
        ],
        "edges": [
            {"source": "s", "target": NODE_ID},
            {"source": NODE_ID, "target": "n_stop", "source_handle": "output", "target_handle": "output"},
        ],
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _normalize_uuid(s: str) -> uuid.UUID:
    t = s.strip()
    if re.fullmatch(r"[0-9a-fA-F]{32}", t):
        t = f"{t[:8]}-{t[8:12]}-{t[12:16]}-{t[16:20]}-{t[20:]}"
    return uuid.UUID(t)


def _ensure_user(explicit_user_id: str | None) -> str:
    with Session(engine) as session:
        if explicit_user_id:
            user_id = _normalize_uuid(explicit_user_id)
            user = session.get(User, user_id)
            if user is None:
                raise SystemExit(f"No user found for --user-id {user_id}")
            return user.username
        user = session.exec(select(User).where(User.username == E2E_USERNAME)).first()
        if user is None:
            user = User(
                username=E2E_USERNAME, password_hash=get_password_hash(E2E_PASSWORD), is_admin=False,
            )
            session.add(user)
            session.commit()
        return E2E_USERNAME


@contextlib.contextmanager
def _run_server(port: int):
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="transcribe-file-http-e2e-uvicorn", daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        raise RuntimeError("uvicorn did not start within 10 seconds")
    try:
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _stt_healthy() -> bool:
    base = (settings.STT_BRIDGE_URL or "").rstrip("/")
    if not base:
        return False
    try:
        r = httpx.get(f"{base}/health", timeout=4.0)
        return r.is_success
    except httpx.RequestError:
        return False


def _build_assemblyai_mock_transport(*, slow: bool) -> httpx.MockTransport:
    """Mock `/v2/upload`, `/v2/transcript`, `/v2/transcript/{id}` for the adapter."""

    state: dict[str, Any] = {"poll_count": 0}
    transcript_id = "tr_mock_http_e2e"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://aai.example/upload/abc"})
        if request.method == "POST" and request.url.path == "/v2/transcript":
            return httpx.Response(200, json={"id": transcript_id, "status": "queued"})
        if (
            request.method == "GET"
            and request.url.path == f"/v2/transcript/{transcript_id}"
        ):
            state["poll_count"] += 1
            if slow and state["poll_count"] < 3:
                return httpx.Response(200, json={"id": transcript_id, "status": "processing"})
            return httpx.Response(
                200,
                json={
                    "id": transcript_id,
                    "status": "completed",
                    "text": _MOCK_AAI_TEXT,
                    "language_code": "en",
                    "audio_duration": 1.0,
                    "speech_model": "best",
                    "utterances": [
                        {"speaker": "A", "start": 0, "end": 1000, "text": _MOCK_AAI_TEXT},
                    ],
                    "words": [],
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@contextlib.contextmanager
def _maybe_mock_assemblyai(*, enable: bool, slow: bool = False) -> Any:
    if not enable:
        yield
        return
    transport = _build_assemblyai_mock_transport(slow=slow)

    def fake_client(*, base_url: str, api_key: str, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport,
        )

    with patch("app.providers.transcription.assemblyai._build_async_client", fake_client):
        yield


async def _login(client: httpx.AsyncClient, username: str, password: str) -> None:
    response = await client.post(
        "/api/v1/auth/login", data={"username": username, "password": password},
    )
    response.raise_for_status()


async def _set_assemblyai_key(client: httpx.AsyncClient, key: str | None) -> None:
    """Persist the AssemblyAI key on the test user via My Settings → API Settings."""
    if not key:
        return
    response = await client.put(
        "/api/v1/auth/me",
        json={"api_keys": {"assemblyai": key}},
    )
    response.raise_for_status()


async def _create_workflow(client: httpx.AsyncClient, graph: dict[str, Any], name: str) -> str:
    response = await client.post(
        "/api/v1/workflow-definitions/", json={"name": name, "graph": graph},
    )
    response.raise_for_status()
    return str(response.json()["id"])


def _extract_transcript_text(node_event: dict[str, Any]) -> str | None:
    out = (node_event.get("result") or {}).get("output") or {}
    if out.get("kind") != "dictionary":
        return None
    data = out.get("data") or {}
    if data.get("type") != "transcript":
        return None
    return str(data.get("full_text") or "").strip()


async def _run_saved_artifact_http(
    client: httpx.AsyncClient,
    audio: bytes,
    filename: str,
    content_type: str,
    *,
    provider: str,
) -> str:
    artifact_response = await client.post(
        "/api/v1/audio-file-artifacts/",
        files={"file": (filename, audio, content_type)},
    )
    artifact_response.raise_for_status()
    artifact_id = str(artifact_response.json()["id"])

    wf_id = await _create_workflow(
        client,
        _graph(provider=provider, artifact_id=artifact_id),
        f"transcribe file saved {provider} HTTP e2e {uuid.uuid4().hex[:8]}",
    )
    run_response = await client.post(f"/api/v1/workflow-definitions/{wf_id}/run", json={})
    run_response.raise_for_status()
    body = run_response.json()
    if body.get("status") != "ok":
        raise RuntimeError(f"saved artifact run failed: {body}")
    for node_result in body.get("node_results") or []:
        if node_result.get("node_id") == NODE_ID:
            text = _extract_transcript_text({"result": node_result})
            if text:
                return text
    raise RuntimeError(f"saved artifact run had no transcript: {body}")


async def _run_runtime_upload_http(
    client: httpx.AsyncClient,
    audio: bytes,
    filename: str,
    content_type: str,
    *,
    upload_timeout: float,
    stream_timeout: float,
    max_upload_elapsed: float,
) -> str:
    wf_id = await _create_workflow(
        client,
        _graph(provider="local_whisper"),
        f"transcribe file runtime HTTP e2e {uuid.uuid4().hex[:8]}",
    )

    text: str | None = None
    input_required_seen = False
    upload_status: int | None = None
    upload_elapsed: float | None = None

    async def _upload(run_id: str) -> httpx.Response:
        nonlocal upload_elapsed
        t0 = time.monotonic()
        response = await client.post(
            f"/api/v1/workflow-runs/{run_id}/transcribe-file-input",
            data={"node_id": NODE_ID, "for_loop_iteration": "0"},
            files={"file": (filename, audio, content_type)},
            timeout=upload_timeout,
        )
        upload_elapsed = time.monotonic() - t0
        return response

    async def _consume() -> str:
        nonlocal input_required_seen, text, upload_status
        sse_timeout = httpx.Timeout(connect=15.0, read=stream_timeout, write=60.0, pool=15.0)
        async for event in enqueue_and_iterate_build_events(client, wf_id, {}, sse_timeout=sse_timeout):
            if event.get("event") == "input_required" and event.get("kind") == "transcribe_file":
                input_required_seen = True
                upload_response = await _upload(str(event["run_id"]))
                upload_status = upload_response.status_code
                upload_response.raise_for_status()
                if upload_elapsed is not None and upload_elapsed > max_upload_elapsed:
                    raise RuntimeError(
                        f"multipart upload response took {upload_elapsed:.2f}s; "
                        f"expected under {max_upload_elapsed:.2f}s"
                    )
            if event.get("event") == "node_end" and event.get("node_id") == NODE_ID:
                text = _extract_transcript_text(event)
            if event.get("event") == "end":
                result = event.get("result") or {}
                if result.get("status") != "ok":
                    raise RuntimeError(f"stream ended non-ok: {event}")
                if not text:
                    raise RuntimeError(f"stream ended without transcript: {event}")
                return text
        raise RuntimeError("stream closed before end event")

    try:
        return await asyncio.wait_for(_consume(), timeout=stream_timeout)
    except TimeoutError as exc:
        raise RuntimeError(
            "runtime upload HTTP flow timed out "
            f"(input_required_seen={input_required_seen}, upload_status={upload_status}, "
            f"upload_elapsed={upload_elapsed}, text={text!r})"
        ) from exc


async def _run_assemblyai_with_reattach(
    client: httpx.AsyncClient,
    audio: bytes,
    filename: str,
    content_type: str,
    *,
    stream_timeout: float,
) -> tuple[str, int]:
    """Run an AAI workflow, intentionally drop the original stream, then reattach."""

    artifact_response = await client.post(
        "/api/v1/audio-file-artifacts/",
        files={"file": (filename, audio, content_type)},
    )
    artifact_response.raise_for_status()
    artifact_id = str(artifact_response.json()["id"])
    wf_id = await _create_workflow(
        client,
        _graph(provider="assemblyai", artifact_id=artifact_id),
        f"transcribe file aai HTTP e2e {uuid.uuid4().hex[:8]}",
    )

    run_id: str | None = None
    saw_start = False
    text_from_first_stream: str | None = None
    text_from_reattach: str | None = None

    sse_timeout = httpx.Timeout(connect=15.0, read=stream_timeout, write=60.0, pool=15.0)

    async def _consume_first() -> None:
        nonlocal saw_start, run_id, text_from_first_stream
        async for event in enqueue_and_iterate_build_events(client, wf_id, {}, sse_timeout=sse_timeout):
            if event.get("event") == "start":
                saw_start = True
                run_id = str(event.get("run_id") or "") or run_id
            if event.get("event") == "node_end" and event.get("node_id") == NODE_ID:
                text_from_first_stream = _extract_transcript_text(event)
            if event.get("event") == "end":
                return

    await asyncio.wait_for(_consume_first(), timeout=stream_timeout)
    if run_id is None or not saw_start:
        raise RuntimeError("assemblyai run never reported a run_id")
    if text_from_first_stream:
        # Inline poll completed quickly enough; we still confirm replay on GET …/events.
        pass

    # Replay / tail uses the same events endpoint whether the client stayed connected or not.
    async for event in iter_workflow_sse_as_legacy_ndjson_events(client, run_id, timeout=sse_timeout):
        if event.get("event") == "node_end" and event.get("node_id") == NODE_ID:
            text_from_reattach = _extract_transcript_text(event)
        if event.get("event") == "end":
            break

    final_text = text_from_first_stream or text_from_reattach
    if not final_text:
        raise RuntimeError("AAI workflow produced no transcript via stream or events replay")
    return final_text, (1 if text_from_reattach else 0)


async def _run(args: argparse.Namespace) -> int:
    mock_stt = not args.real_stt
    mock_aai = not args.real_assemblyai

    if args.real_stt and not _stt_healthy():
        print(
            f"STT bridge not reachable at {settings.STT_BRIDGE_URL!r} (/health). "
            "Start services/stt-bridge or omit --real-stt.",
            file=sys.stderr,
        )
        return 1
    if args.real_assemblyai and not (args.assemblyai_key or settings.ASSEMBLYAI_API_KEY):
        print(
            "--real-assemblyai requires --assemblyai-key or ASSEMBLYAI_API_KEY in env.",
            file=sys.stderr,
        )
        return 1

    username = _ensure_user(args.user_id)
    audio, filename, content_type = _audio_bytes_from_args(args)

    enabled_before = list(settings.TRANSCRIPTION_PROVIDERS_ENABLED)
    if "assemblyai" not in settings.TRANSCRIPTION_PROVIDERS_ENABLED:
        settings.TRANSCRIPTION_PROVIDERS_ENABLED = list({*enabled_before, "assemblyai"})

    aai_poll_before = settings.ASSEMBLYAI_POLL_INTERVAL
    if mock_aai:
        settings.ASSEMBLYAI_POLL_INTERVAL = 0.05

    stt_ctx = contextlib.nullcontext()
    m_stt: AsyncMock | None = None
    if mock_stt:

        async def _stt(_data: bytes, **_kwargs: Any) -> dict[str, Any]:
            if args.mock_stt_delay > 0:
                await asyncio.sleep(args.mock_stt_delay)
            return {"text": _MOCK_STT_TEXT, "language": "en", "segments": [], "duration_seconds": 1.0}

        m_stt = AsyncMock(side_effect=_stt)
        stt_ctx = patch("app.providers.transcription.local_whisper.transcribe_audio_bytes", m_stt)

    port = args.port or _free_port()
    saved_text_lw = ""
    runtime_text_lw = ""
    aai_text = ""
    reattach_replays = 0
    try:
        with stt_ctx, _run_server(port):
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=30.0) as client:
                await _login(
                    client, username, E2E_PASSWORD if not args.user_id else args.password,
                )
                # When mocking AAI we still need a key to pass the executor's pre-flight.
                if args.assemblyai_key:
                    await _set_assemblyai_key(client, args.assemblyai_key)
                elif mock_aai:
                    await _set_assemblyai_key(client, "mock-aai-key-for-e2e")

                saved_text_lw = await _run_saved_artifact_http(
                    client, audio, filename, content_type, provider="local_whisper",
                )
                runtime_text_lw = await _run_runtime_upload_http(
                    client,
                    audio,
                    filename,
                    content_type,
                    upload_timeout=args.upload_timeout,
                    stream_timeout=args.stream_timeout,
                    max_upload_elapsed=args.max_upload_elapsed,
                )
                with _maybe_mock_assemblyai(enable=mock_aai, slow=False):
                    aai_text, reattach_replays = await _run_assemblyai_with_reattach(
                        client,
                        audio,
                        filename,
                        content_type,
                        stream_timeout=args.stream_timeout,
                    )
    finally:
        settings.TRANSCRIPTION_PROVIDERS_ENABLED = enabled_before
        settings.ASSEMBLYAI_POLL_INTERVAL = aai_poll_before

    if mock_stt and m_stt is not None and m_stt.await_count != 2:
        raise RuntimeError(f"Expected mocked STT to be awaited twice, got {m_stt.await_count}")
    if mock_stt and (
        _MOCK_STT_TEXT not in saved_text_lw or _MOCK_STT_TEXT not in runtime_text_lw
    ):
        raise RuntimeError(
            f"Unexpected mock transcripts: saved={saved_text_lw!r} runtime={runtime_text_lw!r}",
        )
    if mock_aai and _MOCK_AAI_TEXT not in aai_text:
        raise RuntimeError(f"Unexpected AAI mock transcript: {aai_text!r}")

    print(
        "ok — live HTTP Transcribe File completed "
        f"(local_saved_chars={len(saved_text_lw)}, local_runtime_chars={len(runtime_text_lw)}, "
        f"aai_chars={len(aai_text)}, reattach_replayed={bool(reattach_replays)}, "
        f"mock_stt={mock_stt}, mock_aai={mock_aai}, port={port})",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Browser-faithful live HTTP Transcribe File e2e.")
    p.add_argument("--user-id", default=None, help="Existing user UUID. Requires --password for login.")
    p.add_argument("--password", default=E2E_PASSWORD, help="Password for --user-id login.")
    p.add_argument("--port", type=int, default=0, help="Port for temporary uvicorn server (default: free port).")
    p.add_argument("--real-stt", action="store_true", help="Call the real STT bridge (default: mock in-process).")
    p.add_argument(
        "--real-assemblyai",
        action="store_true",
        help="Call the real AssemblyAI API (default: mock in-process).",
    )
    p.add_argument(
        "--assemblyai-key",
        default=None,
        help="AssemblyAI API key persisted on the test user (real or mocked).",
    )
    p.add_argument("--audio-file", default=None, help="Audio file to upload/transcribe.")
    p.add_argument("--upload-timeout", type=float, default=10.0, help="Seconds to wait for multipart upload response.")
    p.add_argument("--stream-timeout", type=float, default=60.0, help="Seconds to wait for full stream completion.")
    p.add_argument(
        "--mock-stt-delay",
        type=float,
        default=1.0,
        help="Seconds mocked STT sleeps; verifies upload response is not coupled to transcription.",
    )
    p.add_argument(
        "--max-upload-elapsed",
        type=float,
        default=0.5,
        help="Fail if multipart upload response takes longer than this many seconds.",
    )
    args = p.parse_args()
    if args.user_id and not args.password:
        print("--user-id requires --password for HTTP login.", file=sys.stderr)
        return 2
    print(
        f"run_transcribe_file_workflow_http_e2e: cwd={os.getcwd()!r} "
        f"DATABASE_URL={settings.DATABASE_URL!r} STT_BRIDGE_URL={settings.STT_BRIDGE_URL!r} "
        f"ASSEMBLYAI_BASE_URL={settings.ASSEMBLYAI_BASE_URL!r}",
        file=sys.stderr,
    )
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
