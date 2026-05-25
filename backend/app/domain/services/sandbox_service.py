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
from app.domain.sandbox.fixture_runner import run_fixture_workflow
from app.domain.sandbox.region_trigger_runner import run_region_trigger_workflow
from app.domain.sandbox.region_triggers import evaluate_while_inside_triggers
from app.domain.sandbox.workflow_bridge import graph_requires_simulation_user_action, workflow_graph_node_labels
from app.domain.schemas.documents import DocumentCreate
from app.domain.schemas.sandbox import (
    BoardDefinition,
    SandboxDocumentEnvelope,
    SandboxNestedWorkflowRun,
    SandboxNestedWorkflowRunMeta,
    SandboxPlaybackState,
    SimulationEffects,
)
from app.domain.schemas.workflow_run import WorkflowRunResult
from app.domain.services.board_service import BoardService
from app.domain.services.document_service import DocumentService
from app.domain.services.sandbox_definition_service import item_definition_probe_maps
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.workflow_executor.broadcast_message import append_broadcast_segments_from_run
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
        last_fixture_errors={},
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
            last_fixture_errors={},
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
    ) -> Tuple[
        SandboxDocumentEnvelope,
        bool,
        Dict[str, Optional[WorkflowRunResult]],
        dict[str, Any],
        list[SandboxNestedWorkflowRun],
    ]:
        doc = self._docs.get_document(document_id)
        if not doc or doc.user_id != self.user_id:
            raise ValueError("document not found")

        env = _parse_envelope(doc.body)
        if env.state_version != client_version:
            return env, False, {}, {}, []

        st = env.sandbox.model_copy(deep=True)
        eng = SandboxEngine()
        last_runs: Dict[str, Optional[WorkflowRunResult]] = {}
        nested_runs: list[SandboxNestedWorkflowRun] = []
        simulation_effects = SimulationEffects()
        region_trigger_errors: list[str] = []
        trigger_session = env.region_trigger_state.model_copy(deep=True)

        eng.apply_interactions(st, interactions)
        eng.advance_tick_counter(st)

        wf_svc = WorkflowDefinitionService(self.session, self.user_id)
        executor = WorkflowExecutor(self.session, self.user_id)
        last_errors: Dict[str, Optional[str]] = dict(env.last_errors or {})
        last_fixture_errors: Dict[str, Optional[str]] = dict(env.last_fixture_errors or {})
        user_actions = creature_user_actions or {}
        definition_defaults = item_definition_probe_maps(self.session, self.user_id).defaults

        async def _run_trigger_events(events: list) -> None:
            nonlocal trigger_session
            for event in events:
                creature = next((c for c in st.creatures if c.id == event.creature_id), None)
                if creature is None:
                    region_trigger_errors.append(
                        f"region trigger {event.mode} (region_id={event.region_id}, "
                        f"creature_id={event.creature_id}): creature not found"
                    )
                    continue
                wf = None
                try:
                    wf = wf_svc.get_workflow(uuid.UUID(event.workflow_id))
                except ValueError:
                    pass
                run_result, err = await run_region_trigger_workflow(
                    self.session,
                    self.user_id,
                    st,
                    creature,
                    event,
                    simulation_effects,
                )
                if run_result is not None and wf is not None:
                    region = next(
                        (it for it in st.world.items if it.id == event.region_id and it.type == "region"),
                        None,
                    )
                    region_label = (region.label if region and region.label else event.region_id) or event.region_id
                    nested_runs.append(
                        SandboxNestedWorkflowRun(
                            meta=SandboxNestedWorkflowRunMeta(
                                kind="region_trigger",
                                label=f"Region: {region_label} ({event.mode})",
                                creature_id=creature.id,
                                tick=st.tick,
                                workflow_id=event.workflow_id,
                                region_id=event.region_id,
                                trigger_mode=event.mode,
                                node_labels=workflow_graph_node_labels(wf.graph),
                            ),
                            run=run_result,
                        )
                    )
                if err:
                    region_trigger_errors.append(
                        f"region trigger {event.mode} (region_id={event.region_id}, "
                        f"creature_id={event.creature_id}): {err}"
                    )

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
            creature_label = creature.name.strip() if creature.name and creature.name.strip() else creature.id
            append_broadcast_segments_from_run(
                simulation_effects.broadcast_segments,
                run_result,
                source=f"Creature: {creature_label}",
            )
            dec, perr = eng.parse_workflow_decision(run_result, wf.graph)
            if dec is None:
                last_errors[creature.id] = perr
            elif dec.action == "use_fixture":
                trigger_events, trigger_session = eng.apply_decision(
                    st, creature, dec, region_trigger_session=trigger_session,
                    definition_defaults=definition_defaults,
                )
                await _run_trigger_events(trigger_events)
                from app.domain.sandbox.engine import _fixture_at_cell, _forward_cell

                w, h = st.world.grid.width, st.world.grid.height
                fwd = _forward_cell(creature, w, h)
                if fwd is None:
                    last_fixture_errors[creature.id] = "no forward cell for use_fixture"
                else:
                    fix = _fixture_at_cell(st, fwd)
                    if fix is None:
                        last_fixture_errors[creature.id] = "forward cell has no fixture"
                    else:
                        fx_run, fx_err = await run_fixture_workflow(
                            self.session, self.user_id, st, creature, fix, simulation_effects=simulation_effects
                        )
                        if fx_run is not None:
                            fix_label = fix.label or fix.id
                            fx_workflow_id = ""
                            fx_wf_graph: dict[str, Any] = {}
                            if fix.definition_id:
                                try:
                                    from app.domain.services.sandbox_definition_service import FixtureDefinitionService

                                    fx_def = FixtureDefinitionService(self.session, self.user_id).get(
                                        uuid.UUID(fix.definition_id)
                                    )
                                    fx_workflow_id = fx_def.workflow_id
                                    resolved_fx_wf = wf_svc.get_workflow(uuid.UUID(fx_workflow_id))
                                    if resolved_fx_wf:
                                        fx_wf_graph = resolved_fx_wf.graph if isinstance(resolved_fx_wf.graph, dict) else {}
                                except ValueError:
                                    pass
                            nested_runs.append(
                                SandboxNestedWorkflowRun(
                                    meta=SandboxNestedWorkflowRunMeta(
                                        kind="fixture",
                                        label=f"Fixture: {fix_label}",
                                        creature_id=creature.id,
                                        tick=st.tick,
                                        workflow_id=fx_workflow_id or "",
                                        fixture_id=fix.id,
                                        node_labels=workflow_graph_node_labels(fx_wf_graph),
                                    ),
                                    run=fx_run,
                                )
                            )
                            last_fixture_errors[creature.id] = None
                        elif fx_err:
                            last_fixture_errors[creature.id] = fx_err
            else:
                trigger_events, trigger_session = eng.apply_decision(
                    st, creature, dec, region_trigger_session=trigger_session,
                    definition_defaults=definition_defaults,
                )
                await _run_trigger_events(trigger_events)
                last_errors[creature.id] = None
                last_fixture_errors[creature.id] = None

        while_inside_events = evaluate_while_inside_triggers(st, session_state=trigger_session)
        await _run_trigger_events(while_inside_events)

        env.sandbox = st
        env.last_errors = last_errors
        env.last_fixture_errors = last_fixture_errors
        env.region_trigger_state = trigger_session
        env.last_region_trigger_errors = region_trigger_errors
        if simulation_effects.force_pause:
            playback = dict(env.playback or {})
            playback["paused"] = True
            env.playback = playback
        env.state_version = client_version + 1
        self.save_envelope(document_id, env)
        fresh = self.get_envelope(document_id)
        effects_payload: dict[str, Any] = {"force_pause": simulation_effects.force_pause}
        if simulation_effects.broadcast_segments:
            effects_payload["broadcast_messages"] = list(simulation_effects.broadcast_segments)
        return (fresh if fresh else env), True, last_runs, effects_payload, nested_runs

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
        project_id: Optional[uuid.UUID] = None,
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
            resolved_project_id = project_id
            if resolved_project_id is None and env.board_id:
                source = self._boards.get_board(uuid.UUID(env.board_id))
                if source and not source.is_system:
                    resolved_project_id = source.project_id
            return self._boards.create_board(
                name=board_name,
                definition=defn,
                project_id=resolved_project_id,
            )

        raise ValueError("mode must be 'save_as_new' or 'update_source'")
