"""Sandbox session persistence (document-backed) and tick orchestration."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import Session

from app.domain.document_json import deterministic_json_dumps
from app.domain.sandbox.engine import (
    SandboxEngine,
    board_definition_from_sandbox_state,
    initial_sandbox_state_clean,
    resize_world_grid,
    sandbox_state_from_board,
)
from app.domain.sandbox.workflow_bridge import graph_requires_simulation_user_action
from app.domain.schemas.documents import DocumentCreate
from app.domain.schemas.sandbox import BoardDefinition, SandboxDocumentEnvelope, SandboxPlaybackState
from app.domain.schemas.workflow_run import WorkflowRunResult
from app.domain.services.board_service import BoardService
from app.domain.services.document_service import DocumentService
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.workflow_executor.executor import WorkflowExecutor
from app.persistence.tables import Document, SandboxBoard


def _parse_envelope(body: str) -> SandboxDocumentEnvelope:
    data = json.loads(body) if body.strip() else {}
    return SandboxDocumentEnvelope.model_validate(data)


def _default_envelope(board_id: Optional[str] = None) -> SandboxDocumentEnvelope:
    st = initial_sandbox_state_clean()
    return SandboxDocumentEnvelope(
        board_id=board_id,
        sandbox=st,
        playback=SandboxPlaybackState().model_dump(),
        state_version=1,
        last_errors={},
    )


class SandboxService:
    """Owns sandbox document rows and tick execution."""

    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id
        self._docs = DocumentService(session, user_id)
        self._boards = BoardService(session, user_id)

    def get_document(self, document_id: uuid.UUID) -> Optional[Document]:
        return self._docs.get_document(document_id)

    def create_session(self, board_id: Optional[uuid.UUID] = None) -> Tuple[Document, SandboxDocumentEnvelope]:
        board_svc = self._boards
        bid = board_id or board_svc.get_empty_board_id()
        board_def = board_svc.get_board_definition(bid)
        if board_def is None:
            raise ValueError("board not found")

        wf_svc = WorkflowDefinitionService(self.session, self.user_id)
        for bp in board_def.creatures:
            wf = wf_svc.get_workflow(uuid.UUID(bp.workflow_id))
            if not wf:
                raise ValueError(f"workflow not found for creature: {bp.workflow_id}")

        st = sandbox_state_from_board(board_def)
        env = SandboxDocumentEnvelope(
            board_id=str(bid),
            sandbox=st,
            playback=SandboxPlaybackState().model_dump(),
            state_version=1,
            last_errors={},
        )
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
        creature_user_actions: Optional[Dict[str, dict[str, Any]]] = None,
    ) -> Tuple[SandboxDocumentEnvelope, bool, Dict[str, Optional[WorkflowRunResult]]]:
        doc = self._docs.get_document(document_id)
        if not doc or doc.user_id != self.user_id:
            raise ValueError("document not found")

        env = _parse_envelope(doc.body)
        if env.state_version != client_version:
            return env, False, {}

        st = env.sandbox.model_copy(deep=True)
        eng = SandboxEngine()
        last_runs: Dict[str, Optional[WorkflowRunResult]] = {}

        eng.apply_interactions(st, interactions)
        eng.advance_tick_counter(st)

        wf_svc = WorkflowDefinitionService(self.session, self.user_id)
        executor = WorkflowExecutor(self.session, self.user_id)
        last_errors: Dict[str, Optional[str]] = dict(env.last_errors or {})
        user_actions = creature_user_actions or {}

        for creature in st.creatures:
            wf = wf_svc.get_workflow(uuid.UUID(creature.workflow_id))
            if not wf:
                last_errors[creature.id] = f"workflow not found: {creature.workflow_id}"
                last_runs[creature.id] = None
                continue

            graph_nodes = wf.graph.get("nodes") or []
            requires_user_action = graph_requires_simulation_user_action(graph_nodes)
            creature_action = user_actions.get(creature.id)

            if requires_user_action and not isinstance(creature_action, dict):
                last_errors[creature.id] = (
                    "sandbox_prompt_user_action requires a simulation user action for this tick"
                )
                last_runs[creature.id] = None
                continue

            tick_in = eng.build_tick_input(st, creature)
            input_overrides: dict[str, Any] = {
                "sandbox_tick": tick_in.model_dump(mode="json"),
            }
            if isinstance(creature_action, dict):
                input_overrides["sandbox_user_action"] = creature_action

            run_result = await executor.run(
                wf,
                input_overrides=input_overrides,
            )
            last_runs[creature.id] = run_result
            dec, perr = eng.parse_workflow_decision(run_result, wf.graph)
            if dec is None:
                last_errors[creature.id] = perr
            else:
                eng.apply_decision(st, creature, dec)
                last_errors[creature.id] = None

        env.sandbox = st
        env.last_errors = last_errors
        env.state_version = client_version + 1
        self.save_envelope(document_id, env)
        fresh = self.get_envelope(document_id)
        return (fresh if fresh else env), True, last_runs

    def apply_interactions(
        self,
        document_id: uuid.UUID,
        *,
        interactions: List[dict[str, Any]],
        client_version: int,
    ) -> Tuple[SandboxDocumentEnvelope, bool]:
        doc = self._docs.get_document(document_id)
        if not doc or doc.user_id != self.user_id:
            raise ValueError("document not found")

        env = _parse_envelope(doc.body)
        if env.state_version != client_version:
            return env, False

        pb = SandboxPlaybackState.model_validate(env.playback) if env.playback else SandboxPlaybackState()
        if not pb.paused:
            raise ValueError("playback must be paused to apply interactions")

        st = env.sandbox.model_copy(deep=True)
        SandboxEngine().apply_interactions(st, interactions)
        env.sandbox = st
        env.state_version = client_version + 1
        self.save_envelope(document_id, env)
        fresh = self.get_envelope(document_id)
        return (fresh if fresh else env), True

    def resize_grid(
        self,
        document_id: uuid.UUID,
        *,
        width: int,
        height: int,
        client_version: int,
    ) -> Tuple[SandboxDocumentEnvelope, bool]:
        from app.domain.sandbox.constants import SANDBOX_GRID_MAX_SIZE, SANDBOX_GRID_MIN_SIZE

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

    def save_session_as_board(
        self,
        document_id: uuid.UUID,
        *,
        mode: str,
        name: Optional[str] = None,
    ) -> SandboxBoard:
        doc = self._docs.get_document(document_id)
        if not doc or doc.user_id != self.user_id:
            raise ValueError("document not found")

        env = _parse_envelope(doc.body)
        pb = SandboxPlaybackState.model_validate(env.playback) if env.playback else SandboxPlaybackState()
        if not pb.paused:
            raise ValueError("playback must be paused to save board")

        defn = board_definition_from_sandbox_state(env.sandbox)

        if mode == "update_source":
            if not env.board_id:
                raise ValueError("session has no source board to update")
            board_id = uuid.UUID(env.board_id)
            row = self._boards.get_board(board_id)
            if not row or row.is_system:
                raise ValueError("source board cannot be updated")
            updated = self._boards.update_board(board_id, definition=defn)
            if not updated:
                raise ValueError("failed to update board")
            return updated

        if mode == "save_as_new":
            board_name = (name or "").strip() or f"Board from session {doc.name}"
            return self._boards.create_board(name=board_name, definition=defn)

        raise ValueError("mode must be 'save_as_new' or 'update_source'")
