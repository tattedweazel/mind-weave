"""Sandbox session persistence (document-backed) and tick orchestration."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from sqlmodel import Session

from app.domain.document_json import deterministic_json_dumps
from app.domain.sandbox.builtins import STARTER_SANDBOX_WORKFLOW_ID
from app.domain.sandbox.constants import SANDBOX_GRID_MAX_SIZE, SANDBOX_GRID_MIN_SIZE
from app.domain.sandbox.engine import SandboxEngine, initial_sandbox_state_clean, resize_world_grid
from app.domain.schemas.documents import DocumentCreate
from app.domain.schemas.sandbox import SandboxDocumentEnvelope, SandboxPlaybackState
from app.domain.schemas.workflow_run import WorkflowRunResult
from app.domain.services.document_service import DocumentService
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.workflow_executor.executor import WorkflowExecutor
from app.persistence.tables import Document


def _parse_envelope(body: str) -> SandboxDocumentEnvelope:
    data = json.loads(body) if body.strip() else {}
    return SandboxDocumentEnvelope.model_validate(data)


def _default_envelope(workflow_id: uuid.UUID) -> SandboxDocumentEnvelope:
    st = initial_sandbox_state_clean()
    return SandboxDocumentEnvelope(
        workflow_id=str(workflow_id),
        sandbox=st,
        playback=SandboxPlaybackState().model_dump(),
        state_version=1,
        last_error=None,
    )


def _apply_sandbox_defaults_from_graph(env: SandboxDocumentEnvelope, graph: dict) -> None:
    """If ``graph`` contains ``sandbox_defaults``, resize the initial grid (min/max enforced)."""
    sd = graph.get("sandbox_defaults")
    if not isinstance(sd, dict):
        return
    gw = sd.get("grid_width")
    gh = sd.get("grid_height")
    if gw is None or gh is None:
        return
    try:
        w_i, h_i = int(gw), int(gh)
    except (TypeError, ValueError):
        return
    w_i = max(SANDBOX_GRID_MIN_SIZE, min(SANDBOX_GRID_MAX_SIZE, w_i))
    h_i = max(SANDBOX_GRID_MIN_SIZE, min(SANDBOX_GRID_MAX_SIZE, h_i))
    resize_world_grid(env.sandbox, w_i, h_i)


class SandboxService:
    """Owns sandbox document rows and tick execution."""

    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id
        self._docs = DocumentService(session, user_id)

    def get_starter_workflow_id(self) -> uuid.UUID:
        return STARTER_SANDBOX_WORKFLOW_ID

    def get_document(self, document_id: uuid.UUID) -> Optional[Document]:
        return self._docs.get_document(document_id)

    def create_session(self, workflow_id: Optional[uuid.UUID] = None) -> Tuple[Document, SandboxDocumentEnvelope]:
        wf_id = workflow_id or STARTER_SANDBOX_WORKFLOW_ID
        wf_svc = WorkflowDefinitionService(self.session, self.user_id)
        wf = wf_svc.get_workflow(wf_id)
        if not wf:
            raise ValueError("workflow not found")

        env = _default_envelope(wf_id)
        graph = wf.graph if isinstance(wf.graph, dict) else {}
        _apply_sandbox_defaults_from_graph(env, graph)
        body = deterministic_json_dumps(env.model_dump(mode="json"))
        doc = self._docs.create_document(
            DocumentCreate(
                name=f"Sandbox Session {uuid.uuid4().hex[:8]}",
                description="Sandbox simulation state",
                body=body,
            )
        )
        return doc, env

    def get_envelope(self, document_id: uuid.UUID) -> Optional[SandboxDocumentEnvelope]:
        doc = self._docs.get_document(document_id)
        if not doc:
            return None
        return _parse_envelope(doc.body)

    def save_envelope(self, document_id: uuid.UUID, env: SandboxDocumentEnvelope) -> bool:
        doc = self._docs.get_document(document_id)
        if not doc or doc.user_id != self.user_id:
            return False
        doc.body = deterministic_json_dumps(env.model_dump(mode="json"))
        doc.updated_at = datetime.now(timezone.utc)
        self.session.add(doc)
        self.session.commit()
        self.session.refresh(doc)
        return True

    async def run_tick(
        self,
        document_id: uuid.UUID,
        *,
        interactions: List[dict[str, Any]],
        client_version: int,
        workflow_id_override: Optional[uuid.UUID] = None,
    ) -> Tuple[SandboxDocumentEnvelope, bool, Optional[WorkflowRunResult]]:
        """
        Run one tick. Returns (envelope, ok, last_workflow_run).
        last_workflow_run is set only when this tick invoked WorkflowExecutor.run (not intent-continuation-only).
        On version mismatch, ok is False and last_workflow_run is None.
        """
        doc = self._docs.get_document(document_id)
        if not doc or doc.user_id != self.user_id:
            raise ValueError("document not found")

        env = _parse_envelope(doc.body)
        if env.state_version != client_version:
            return env, False, None

        wf_raw = workflow_id_override or env.workflow_id
        wf_id = wf_raw if isinstance(wf_raw, uuid.UUID) else uuid.UUID(str(wf_raw))
        wf_svc = WorkflowDefinitionService(self.session, self.user_id)
        wf = wf_svc.get_workflow(wf_id)
        if not wf:
            raise ValueError("workflow not found")

        if workflow_id_override is not None:
            env.workflow_id = str(workflow_id_override)

        st = env.sandbox.model_copy(deep=True)
        eng = SandboxEngine()
        last_run: Optional[WorkflowRunResult] = None

        eng.apply_interactions(st, interactions)
        eng.passive_tick_start(st)
        eng.advance_tick_counter(st)

        if st.pet.intent and st.pet.intent.status == "in_progress":
            eng.continue_intent_step(st)
            env.last_error = None
        else:
            tick_in = eng.build_tick_input(st)
            executor = WorkflowExecutor(self.session, self.user_id)
            run_result = await executor.run(
                wf,
                input_overrides={"sandbox_tick": tick_in.model_dump(mode="json")},
            )
            last_run = run_result
            dec, perr = eng.parse_workflow_decision(run_result, wf.graph)
            if dec is None:
                env.last_error = perr
            else:
                eng.start_intent_from_decision(st, dec)
                if st.pet.intent and st.pet.intent.status == "in_progress":
                    eng.continue_intent_step(st)
                env.last_error = None

        env.sandbox = st
        env.state_version = client_version + 1
        self.save_envelope(document_id, env)
        fresh = self.get_envelope(document_id)
        return (fresh if fresh else env), True, last_run

    def resize_grid(
        self,
        document_id: uuid.UUID,
        *,
        width: int,
        height: int,
        client_version: int,
    ) -> Tuple[SandboxDocumentEnvelope, bool]:
        """Resize world grid when playback is paused. Returns (envelope, ok); ok False on version mismatch."""
        doc = self._docs.get_document(document_id)
        if not doc or doc.user_id != self.user_id:
            raise ValueError("document not found")

        env = _parse_envelope(doc.body)
        if env.state_version != client_version:
            return env, False

        pb = SandboxPlaybackState.model_validate(env.playback) if env.playback else SandboxPlaybackState()
        if not pb.paused:
            raise ValueError("playback must be paused to resize the grid")

        try:
            w_i, h_i = int(width), int(height)
        except (TypeError, ValueError) as exc:
            raise ValueError("width and height must be integers") from exc
        if w_i < SANDBOX_GRID_MIN_SIZE or h_i < SANDBOX_GRID_MIN_SIZE:
            raise ValueError(f"grid dimensions must be at least {SANDBOX_GRID_MIN_SIZE}x{SANDBOX_GRID_MIN_SIZE}")
        if w_i > SANDBOX_GRID_MAX_SIZE or h_i > SANDBOX_GRID_MAX_SIZE:
            raise ValueError(f"grid dimensions must be at most {SANDBOX_GRID_MAX_SIZE}x{SANDBOX_GRID_MAX_SIZE}")

        st = env.sandbox.model_copy(deep=True)
        resize_world_grid(st, w_i, h_i)
        env.sandbox = st
        env.state_version = client_version + 1
        self.save_envelope(document_id, env)
        fresh = self.get_envelope(document_id)
        return (fresh if fresh else env), True
