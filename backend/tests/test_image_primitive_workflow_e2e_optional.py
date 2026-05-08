"""
Optional end-to-end: Image primitive + Multimodal LLM with a real LM Studio call (no provider mock).

Set RUN_IMAGE_E2E=1 and run a local LM Studio instance reachable at ``LMSTUDIO_BASE_URL`` (default
``http://127.0.0.1:1234/v1``) with a **vision-capable** model matching the test Persona default.

Example::

  cd backend && RUN_IMAGE_E2E=1 uv run pytest tests/test_image_primitive_workflow_e2e_optional.py -v
"""

from __future__ import annotations

import base64
import os
import uuid

import httpx
import pytest
from sqlmodel import Session, select

from app.core.config import settings
from app.domain.services.workflow_executor import WorkflowExecutor
from app.persistence.tables import Persona, UrlSnapshotArtifact, User, WorkflowDefinition

_MIN_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+lmfkAAAAASUVORK5CYII="
)


@pytest.mark.asyncio
async def test_image_primitive_to_multimodal_real_lm_studio(db_session: Session):
    if os.environ.get("RUN_IMAGE_E2E") != "1":
        pytest.skip("Set RUN_IMAGE_E2E=1 and start LM Studio with a vision model (see module docstring).")

    base = settings.LMSTUDIO_BASE_URL.rstrip("/")
    try:
        r = httpx.get(f"{base}/models", timeout=5.0)
        r.raise_for_status()
    except Exception as e:
        pytest.skip(f"LM Studio not reachable at {base}: {e}")

    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None

    art = UrlSnapshotArtifact(
        user_id=user.id,
        image_bytes=_MIN_PNG,
        mime_type="image/png",
        width=1,
        height=1,
        final_url="",
    )
    db_session.add(art)
    db_session.commit()
    db_session.refresh(art)

    persona = db_session.exec(select(Persona).limit(1)).first()
    assert persona is not None

    wf_id = uuid.uuid4()
    graph = {
        "nodes": [
            {"id": "s", "kind": "start", "label": "S", "data": {"text": ""}, "position": {}},
            {
                "id": "n_img",
                "kind": "primitive",
                "primitive_type": "image",
                "label": "Image",
                "data": {
                    "label": "Image",
                    "artifact_id": str(art.id),
                    "required_inputs": [{"key": "image", "type": "dictionary", "value": None}],
                },
                "position": {},
            },
            {
                "id": "n_t",
                "kind": "primitive",
                "primitive_type": "string",
                "label": "T",
                "data": {"text": "What is in this image? One word."},
                "position": {},
            },
            {
                "id": "n_mm",
                "kind": "skill",
                "skill_type": "multimodal_llm",
                "label": "MM",
                "data": {
                    "persona_id": str(persona.id),
                    "required_inputs": [
                        {"key": "user_prompt", "type": "string", "value": None},
                        {"key": "images", "type": "list", "value": None},
                    ],
                },
                "position": {},
            },
            {
                "id": "st",
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                "position": {},
            },
        ],
        "edges": [
            {"source": "s", "target": "n_img"},
            {"source": "s", "target": "n_t"},
            {"source": "n_img", "target": "n_mm", "source_handle": "output", "target_handle": "images"},
            {"source": "n_t", "target": "n_mm", "target_handle": "user_prompt"},
            {"source": "n_mm", "target": "st", "source_handle": "output", "target_handle": "output"},
        ],
    }
    db_session.add(WorkflowDefinition(id=wf_id, user_id=user.id, name="E2E image multimodal", graph=graph))
    db_session.commit()

    wf_row = db_session.get(WorkflowDefinition, wf_id)
    assert wf_row is not None
    ex = WorkflowExecutor(db_session, user.id)
    result = await ex.run(wf_row)

    assert result.status == "ok", getattr(result, "error", None)
    mm = next(nr for nr in result.node_results if nr.node_id == "n_mm" and nr.status == "ok")
    assert mm.output is not None
    # Response or dictionary depending on structure
    assert getattr(mm.output, "text", None) or (getattr(mm.output, "data", None) is not None)
