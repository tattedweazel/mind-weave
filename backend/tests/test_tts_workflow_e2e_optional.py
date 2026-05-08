"""
End-to-end: WorkflowExecutor + real HTTP to tts-bridge (no synthesis mocks).

Set RUN_TTS_E2E=1 and run tts-bridge on TTS_BRIDGE_URL (default http://127.0.0.1:8765) with
TTS_MODEL_ROOT matching this repo, TTS_BRIDGE_MOCK=0. Optionally set TTS_E2E_MODEL_KEY.

**Default local_key**: prefers a **Base** checkpoint (``config.json`` → ``tts_model_type == "base"``) so we
exercise the same Qwen3-TTS + speech_tokenizer (12Hz) path that voice clone / many prod workflows use.
The Voice Design-only snapshot sorted first by name is **not** enough coverage.

Before starting the bridge, ensure nothing else is already bound to the bridge port
(default **8765**), or you will connect to a **stale** process and see confusing errors
(e.g. meta tensor) even after upgrading code: ``lsof -i :8765`` then stop the old PID.

Example:
  (terminal 1) cd services/tts-bridge && TTS_MODEL_ROOT=../../.local/tts-models TTS_BRIDGE_MOCK=0 \\
    .venv/bin/uvicorn tts_bridge.main:app --host 127.0.0.1 --port 8765
  (terminal 2) cd backend && RUN_TTS_E2E=1 uv run pytest tests/test_tts_workflow_e2e_optional.py -v

``GET /health`` on the bridge includes **qwen_torch_cache_revision**; after a code change, that
string must change — if it does not, you are not talking to the new build.
"""

from __future__ import annotations

import base64
import io
import json
import os
import uuid
import wave
from pathlib import Path

import httpx
import pytest
from sqlmodel import Session, select

from app.domain.services.workflow_executor import WorkflowExecutor
from app.persistence.tables import TtsModelArtifact, User, WorkflowDefinition

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO / ".local" / "tts-models"


def _mini_wav_base64() -> str:
    """~1s of silence at 24 kHz so Qwen3-TTS reference encoding has enough samples for its convs."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24_000)
        w.writeframes(b"\x00\x00" * 24_000)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _discover_model_key() -> str:
    key = (os.environ.get("TTS_E2E_MODEL_KEY") or "").strip()
    if key:
        return key
    root = Path(os.environ.get("TTS_E2E_MODEL_ROOT", str(DEFAULT_ROOT)))
    gs = sorted((root / "qwen_torch").glob("*/config.json")) if (root / "qwen_torch").is_dir() else []
    candidates: list[Path] = []
    for cfg in gs:
        base = cfg.parent
        if (base / "speech_tokenizer" / "config.json").is_file():
            candidates.append(base)
    if not candidates:
        raise RuntimeError(f"No qwen_torch snapshot under {root} (need config + speech_tokenizer)")

    for base in candidates:
        try:
            with open(base / "config.json", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if str(meta.get("tts_model_type") or "").lower() == "base":
            return f"qwen_torch/{base.name}"

    return f"qwen_torch/{candidates[0].name}"


@pytest.mark.asyncio
async def test_tts_e2e_workflow_executor_real_bridge(
    client,  # noqa: ARG001
    db_session: Session,
):
    if os.environ.get("RUN_TTS_E2E") != "1":
        pytest.skip("Set RUN_TTS_E2E=1 and run tts-bridge with real weights (see module docstring).")

    from app.core.config import settings

    base = settings.TTS_BRIDGE_URL.rstrip("/")
    try:
        r = httpx.get(f"{base}/health", timeout=5.0)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001 — smoke reachability
        pytest.skip(f"TTS bridge not reachable at {base}: {e}")

    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    uid = user.id

    mkey = _discover_model_key()
    tts_data: dict = {
        "tts_model_id": None,  # set after artifact id
        "required_inputs": [{"key": "text", "type": "string", "value": "E2E workflow TTS line."}],
        "tts_options": {
            "language": "English",
            "ref_text": "E2E reference line for voice clone",
            "ref_audio_base64": _mini_wav_base64(),
        },
    }
    aid = uuid.uuid4()
    tts_data["tts_model_id"] = str(aid)
    db_session.add(
        TtsModelArtifact(
            id=aid,
            display_name="E2E TTS",
            engine="qwen_torch",
            source={"kind": "huggingface_repo", "repo_id": "e2e/local"},
            local_key=mkey,
            status="ready",
            error_message=None,
        )
    )
    wf_id = uuid.uuid4()
    graph = {
        "nodes": [
            {"id": "s", "kind": "start", "label": "S", "data": {"text": ""}, "position": {}},
            {
                "id": "tts",
                "kind": "skill",
                "skill_type": "text_to_speech",
                "label": "TTS",
                "data": tts_data,
                "position": {},
            },
            {
                "id": "st",
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "audio"}]},
                "position": {},
            },
        ],
        "edges": [
            {"source": "s", "target": "tts"},
            {"source": "tts", "target": "st", "source_handle": "output", "target_handle": "output"},
        ],
    }
    db_session.add(WorkflowDefinition(id=wf_id, user_id=uid, name="E2E TTS", graph=graph))
    db_session.commit()

    wf_row = db_session.get(WorkflowDefinition, wf_id)
    assert wf_row is not None

    ex = WorkflowExecutor(db_session, uid)
    result = await ex.run(wf_row)

    assert result.status == "ok", f"{getattr(result, 'error', None)} {getattr(result, 'node_results', None)}"
    tts_ok = [nr for nr in result.node_results if nr.node_id == "tts" and nr.status == "ok"]
    assert len(tts_ok) == 1
    out = tts_ok[0].output
    assert out is not None
    assert getattr(out, "kind", None) == "audio"
    assert len((out.audio_base64 or "")) > 100
