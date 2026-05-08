"""FastAPI TTS bridge."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from tts_bridge.config import settings
from tts_bridge.engines.qwen_torch import TTS_QWEN_LOAD_CACHE_REVISION
from tts_bridge.engines.registry import get_engine
from tts_bridge.wav_util import minimal_silent_wav

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mind Weave TTS Bridge", version="0.1.0")


def _is_pytorch_meta_device_notimplemented(exc: BaseException) -> bool:
    """
    PyTorch raises NotImplementedError (not RuntimeError) for illegal copies from the meta device,
    e.g. \"Cannot copy out of meta tensor; no data!\". Those are synthesis/weight materialization
    bugs — map them to HTTP 500, not 501 (reserved for unimplemented *engines* like qwen_mlx stub).
    """
    if not isinstance(exc, NotImplementedError):
        return False
    msg = str(exc).lower()
    return "meta tensor" in msg or "to_empty()" in msg

api_key_header = APIKeyHeader(name="X-TTS-Bridge-Token", auto_error=False)


def verify_token(x_tts_bridge_token: str | None = Depends(api_key_header)) -> None:
    expected = (settings.TTS_BRIDGE_TOKEN or "").strip()
    if not expected:
        return
    if (x_tts_bridge_token or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-TTS-Bridge-Token")


class PullRequest(BaseModel):
    engine: str
    artifact_id: str = Field(..., min_length=1)
    source: dict[str, Any]


class PullResponse(BaseModel):
    local_key: str


class TtsRequest(BaseModel):
    engine: str
    model_local_key: str = Field(..., min_length=1)
    text: str
    options: dict[str, Any] = Field(default_factory=dict)
    response_format: Literal["wav", "base64_json"] = "wav"


class HealthResponse(BaseModel):
    status: str
    mock: bool
    model_root: str
    engines: list[str]
    qwen_torch_cache_revision: str


@app.get("/health", response_model=HealthResponse)
def health():
    root = Path(settings.TTS_MODEL_ROOT)
    return HealthResponse(
        status="ok",
        mock=bool(settings.TTS_BRIDGE_MOCK),
        model_root=str(root.resolve()),
        engines=["qwen_torch", "qwen_mlx"],
        qwen_torch_cache_revision=TTS_QWEN_LOAD_CACHE_REVISION,
    )


@app.post("/v1/models/pull", response_model=PullResponse, dependencies=[Depends(verify_token)])
def pull_model(body: PullRequest):
    eng = get_engine(body.engine)
    try:
        local_key = eng.pull(body.artifact_id, body.source)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    except Exception as e:
        logger.exception("pull failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
    return PullResponse(local_key=local_key)


@app.post("/v1/tts", dependencies=[Depends(verify_token)])
def synthesize(body: TtsRequest):
    if len(body.text) > settings.TTS_MAX_TEXT_CHARS:
        raise HTTPException(status_code=400, detail="text too long")
    eng = get_engine(body.engine)
    try:
        audio = eng.synthesize(body.model_local_key, body.text, body.options or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except NotImplementedError as e:
        if _is_pytorch_meta_device_notimplemented(e):
            logger.exception("synthesize failed (meta tensor / device materialization)")
            raise HTTPException(status_code=500, detail=str(e)) from e
        raise HTTPException(status_code=501, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("synthesize failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    if len(audio) > settings.TTS_MAX_AUDIO_BYTES:
        raise HTTPException(status_code=500, detail="generated audio exceeds TTS_MAX_AUDIO_BYTES")

    if body.response_format == "base64_json":
        return {
            "mime_type": "audio/wav",
            "audio_base64": base64.b64encode(audio).decode("ascii"),
        }
    return Response(content=audio, media_type="audio/wav")


@app.get("/v1/mock-wav")
def mock_wav():
    """Tiny WAV for client smoke tests."""
    return Response(content=minimal_silent_wav(), media_type="audio/wav")
