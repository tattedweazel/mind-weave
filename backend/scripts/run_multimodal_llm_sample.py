#!/usr/bin/env python3
"""
Insert a **temporary** workflow (List + String → **multimodal_llm** → Stop) with a seeded
**url_snapshot_artifacts** PNG row, run **WorkflowExecutor** once, and print the multimodal step reply.

``chdir`` to ``backend/`` before imports so ``DATABASE_URL`` and ``.env`` match **uvicorn**.

**Default:** mocks ``LMStudioProvider.chat`` — **no** HTTP to LM Studio (safe for CI/agents).

**``--real-llm``:** calls the configured LM Studio instance; use a **vision-capable** model loaded
there (or set ``data.model`` on the node). See **docs/OPERATIONS.md** (*Offline script (multimodal_llm sample)*).

Example::

  cd backend && uv run python scripts/run_multimodal_llm_sample.py

Reuse the printed **workflow id** with::

  uv run python scripts/run_workflow_stream.py --workflow-id <uuid>

Pass **``--cleanup``** to delete the created **user**, **artifact**, and **workflow** after the run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
os.chdir(_BACKEND_ROOT)

from sqlmodel import Session, select

from app.domain.services.persona_service import PersonaService
from app.domain.workflow_executor.executor import WorkflowExecutor
from app.persistence.db import engine
from app.persistence.tables import Persona, UrlSnapshotArtifact, User, WorkflowDefinition
from app.providers.base import ProviderResponse

_MINI_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _graph(persona_id: str, artifact_id: str) -> dict:
    return {
        "nodes": [
            {
                "id": "n_l",
                "kind": "primitive",
                "primitive_type": "list",
                "label": "Images",
                "data": [{"artifact_id": artifact_id}],
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "n_s",
                "kind": "primitive",
                "primitive_type": "string",
                "label": "Prompt",
                "data": {"text": "Describe this 1×1 PNG in one short phrase."},
                "position": {"x": 0, "y": 120},
            },
            {
                "id": "n_mm",
                "kind": "skill",
                "skill_type": "multimodal_llm",
                "label": "Multimodal LLM",
                "data": {
                    "persona_id": persona_id,
                    "required_inputs": [
                        {"key": "user_prompt", "type": "string", "value": None},
                        {"key": "images", "type": "list", "value": None},
                    ],
                },
                "position": {"x": 280, "y": 60},
            },
            {
                "id": "n_stop",
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "string"}]},
                "position": {"x": 520, "y": 60},
            },
        ],
        "edges": [
            {"source": "n_l", "target": "n_mm", "target_handle": "images"},
            {"source": "n_s", "target": "n_mm", "target_handle": "user_prompt"},
            {"source": "n_mm", "target": "n_stop"},
        ],
    }


async def _run(*, cleanup: bool, real_llm: bool) -> int:
    uid = uuid.uuid4()
    wf_id = uuid.uuid4()
    user = User(
        id=uid,
        username=f"mm_sample_{uid.hex[:8]}",
        password_hash="multimodal_sample",
        is_admin=False,
    )
    art = UrlSnapshotArtifact(
        user_id=uid,
        image_bytes=_MINI_PNG_1X1,
        mime_type="image/png",
        width=1,
        height=1,
        final_url="",
    )
    with Session(engine) as session:
        PersonaService(session).initialize_default_personas()
        persona = session.exec(select(Persona).where(Persona.name == "default")).first()
        if persona is None:
            print("No default persona after seeding; check PersonaService.", file=sys.stderr)
            return 1

        session.add(user)
        session.add(art)
        session.commit()
        session.refresh(art)

        graph = _graph(str(persona.id), str(art.id))
        wf_row = WorkflowDefinition(
            id=wf_id,
            user_id=uid,
            name="Sample: multimodal_llm + seeded PNG artifact",
            graph=graph,
        )
        session.add(wf_row)
        session.commit()

        wf = session.get(WorkflowDefinition, wf_id)
        assert wf is not None
        ex = WorkflowExecutor(session, uid)

        mock_response = ProviderResponse(
            raw_text="[mock] A single dark pixel on transparency.",
            parsed=None,
            provider_name="lmstudio",
            usage={"input_tokens": 10, "output_tokens": 12},
        )

        if real_llm:
            result = await ex.run(wf)
        else:
            with patch("app.domain.workflow_executor.executor.LMStudioProvider") as MockProvider:
                mock_instance = AsyncMock()
                mock_instance.chat = AsyncMock(return_value=mock_response)
                MockProvider.return_value = mock_instance
                result = await ex.run(wf)

        if cleanup:
            session.delete(wf_row)
            session.delete(art)
            session.delete(user)
            session.commit()

    print(f"Run status: {result.status}", file=sys.stderr)
    print(f"Workflow id (for run_workflow_stream.py): {wf_id}", file=sys.stderr)
    for nr in result.node_results:
        if nr.node_id == "n_mm" and nr.status == "ok" and nr.output is not None:
            out = nr.output
            text = getattr(out, "text", None)
            if text is not None:
                print(text)
            else:
                print(json.dumps(getattr(out, "data", out), indent=2, ensure_ascii=False, default=str))
            return 0 if result.status == "ok" else 1

    print("multimodal_llm node not found or failed", file=sys.stderr)
    for nr in result.node_results:
        print(f"  {nr.node_id} {nr.status} {nr.error!r}", file=sys.stderr)
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="Run multimodal_llm sample with a seeded PNG artifact.")
    p.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete the created user, artifact, and workflow after the run.",
    )
    p.add_argument(
        "--real-llm",
        action="store_true",
        help="Do not mock LM Studio; requires a reachable LMSTUDIO_BASE_URL and a vision model.",
    )
    args = p.parse_args()
    return asyncio.run(_run(cleanup=args.cleanup, real_llm=args.real_llm))


if __name__ == "__main__":
    raise SystemExit(main())
