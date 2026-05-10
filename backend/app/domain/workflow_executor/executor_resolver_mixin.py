"""`_resolve_*` node evaluation and For-loop orchestration extracted from executor.py."""

import asyncio
import contextlib
import json
import secrets
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, cast
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from sqlalchemy import or_
from sqlmodel import col, select

from app.core.config import settings
from app.core.run_log_redaction import redact_node_log_for_storage
from app.domain.document_json import deterministic_json_dumps
from app.domain.sandbox.constants import DECISION_ACTION_STRINGS
from app.domain.schemas import (
    AddDaysUtilityNode,
    AddToListUtilityNode,
    AndControlNode,
    AppendValueToDocumentUtilityNode,
    BasicConditionalControlNode,
    BetweenControlNode,
    BooleanNodeOutput,
    BooleanPrimitiveNode,
    ConditionalNodeOutput,
    DateTimeNodeOutput,
    DateTimePrimitiveNode,
    DecisionActionPrimitiveNode,
    DictionaryNodeOutput,
    DictionaryPrimitiveNode,
    DictionarySetValueByKeyUtilityNode,
    DictionaryValueByKeyUtilityNode,
    DocumentNodeOutput,
    DocumentPrimitiveNode,
    ForLoopControlNode,
    ForLoopEndControlNode,
    GmailNodeOutput,
    GmailPrimitiveNode,
    GraphEdge,
    GtControlNode,
    GteControlNode,
    HtmlParseBasicUtilityNode,
    ImagePrimitiveNode,
    IntNodeOutput,
    IntPrimitiveNode,
    IntToStringUtilityNode,
    IsControlNode,
    IsEmptyControlNode,
    LenFromListUtilityNode,
    ListItemByIndexUtilityNode,
    ListNodeOutput,
    ListPrimitiveNode,
    ListToStringUtilityNode,
    LoadDocumentUtilityNode,
    LtControlNode,
    LteControlNode,
    MessageUtilityNode,
    NodeOutputUnion,
    NodeRunResult,
    NotControlNode,
    OrControlNode,
    ParseDocumentBodyUtilityNode,
    PrependTextUtilityNode,
    RandomItemFromListUtilityNode,
    ReadDocumentPropertyUtilityNode,
    ResponseNodeOutput,
    SandboxAvailableCellsUtilityNode,
    SandboxBehaviorPrimitiveNode,
    SandboxClosestItemUtilityNode,
    SandboxDecisionIntentUtilityNode,
    SandboxDecisionMoveToUtilityNode,
    SandboxFilterItemsByTypeUtilityNode,
    SandboxFirstFoodWorldOrderUtilityNode,
    SandboxFirstNearbyFoodUtilityNode,
    SandboxIsNearby8UtilityNode,
    SandboxNearestItemByTypeUtilityNode,
    SandboxPetCellUtilityNode,
    SandboxPetEnergyUtilityNode,
    SandboxPetHungerUtilityNode,
    SandboxStarterDecisionUtilityNode,
    SandboxTickItemsUtilityNode,
    SandboxTickPetUtilityNode,
    SandboxTickPrimitiveNode,
    SandboxWorldGridUtilityNode,
    StartGraphNode,
    StartNodeOutput,
    StopGraphNode,
    StopNodeOutput,
    StringNodeOutput,
    StringPrimitiveNode,
    StringToListUtilityNode,
    StringTruncUtilityNode,
    StructureNodeOutput,
    StructurePrimitiveNode,
    TryCatchControlNode,
    UpsertDocumentUtilityNode,
    ValidateAgainstStructureUtilityNode,
    WorkflowRefNode,
    WriteObjectToDocumentBodyUtilityNode,
    XorControlNode,
    gmail_dict_to_node_output,
)
from app.domain.schemas.sandbox import DecisionIntent, GridCell, SandboxTickInput
from app.domain.services.document_service import DocumentService
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.workflow_executor.aux_outputs import record_for_loop_summary
from app.domain.workflow_executor.html_parse_basic import parse_html_basic
from app.domain.workflow_output_overrides import filter_output_overrides_for_graph
from app.persistence.tables import (
    Document,
    NodeRunLog,
    Structure,
    UrlSnapshotArtifact,
    WorkflowDefinition,
)

from .dispatch import ExecutionNodeContext, dispatch_execute_node
from .graph import (
    _build_in_degree_and_adjacency,
    _topological_order,
    for_loop_body_node_ids,
    try_catch_catch_region,
    try_catch_catch_seeds,
    try_catch_try_region,
)
from .helpers import (
    _condition_to_bool,
    _format_exception,
    _to_comparable,
    _values_equal,
    parse_rfc3339_datetime_string,
    parse_strict_int_for_slot,
    pop_wave_batch,
    shift_rfc3339_instant_by_days,
    split_batch_isolating_audio_steps,
    utc_now_rfc3339_normalized_for_executor,
)
from .inputs import (
    _get_slot_value,
    _resolve_inputs_by_target_handle,
    _resolve_upstream_for_node,
    node_output_to_input_override_value,
)
from .output_explorer import attach_output_explorer_after_redact, merge_details_with_output_explorer


def _executor_mod():
    """Late import avoids circular imports with ``executor``."""
    import app.domain.workflow_executor.executor as mod

    return mod


class WorkflowExecutorResolverMixin:
    def _coerce_list_value_for_for_loop(self, raw: Any) -> List[Any]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        try:
            return list(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return []

    def _resolve_for_loop_list(
        self,
        node: ForLoopControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> List[Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "input", "type": "list", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["input"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        data = resolved.get("input")
        return self._coerce_list_value_for_for_loop(data)

    def _item_json_to_node_output(self, node_id: str, item: Any) -> NodeOutputUnion:
        if isinstance(item, str):
            return StringNodeOutput(node_id=node_id, text=item)
        if isinstance(item, list):
            return ListNodeOutput(node_id=node_id, data=item)
        if isinstance(item, dict):
            return DictionaryNodeOutput(node_id=node_id, data=item)
        if isinstance(item, int):
            return IntNodeOutput(node_id=node_id, value=item)
        if isinstance(item, bool):
            return BooleanNodeOutput(node_id=node_id, value=item)
        return StringNodeOutput(node_id=node_id, text=str(item))

    @staticmethod
    def _for_loop_iteration_mode(node: ForLoopControlNode) -> str:
        data = node.data or {}
        raw = data.get("iteration_mode")
        if isinstance(raw, str):
            m = raw.strip().lower()
            if m in ("sequential", "parallel", "batched"):
                return m
        if data.get("parallel_iterations") is True:
            return "parallel"
        return "sequential"

    @staticmethod
    def _for_loop_continue_on_error(node: ForLoopControlNode) -> bool:
        return (node.data or {}).get("continue_on_error") is True

    def _for_loop_parallel_chunk_size(self, node: ForLoopControlNode, mode: str) -> int:
        if mode == "batched":
            raw_bs = (node.data or {}).get("batch_size", settings.WORKFLOW_DEFAULT_LOOP_BATCH_SIZE)
            try:
                bs = int(raw_bs)
            except (TypeError, ValueError):
                bs = settings.WORKFLOW_DEFAULT_LOOP_BATCH_SIZE
            return max(1, min(bs, settings.WORKFLOW_MAX_LOOP_BATCH_SIZE_CEILING))
        return self._wave_cap_for_run()

    @staticmethod
    def _slice_for_loop_max_iterations_node(node: ForLoopControlNode, items: list[Any]) -> list[Any]:
        raw = (node.data or {}).get("max_iterations")
        if raw is None:
            return items
        try:
            cap = max(1, int(raw))
        except (TypeError, ValueError):
            return items
        return items[:cap]

    def _for_loop_record_summary(
        self,
        loop_node_id: str,
        *,
        processed: int,
        results_track: List[Any],
        errors_track: List[Dict[str, Any]],
    ) -> None:
        items_failed = sum(1 for v in results_track if v is None)
        record_for_loop_summary(
            loop_node_id,
            {
                "items_processed": processed,
                "items_failed": items_failed,
                "results": list(results_track),
                "errors": list(errors_track),
            },
        )

    def _for_loop_iteration_item_primitive(self, node_id: str, raw_item: Any) -> Any:
        return node_output_to_input_override_value(self._item_json_to_node_output(node_id, raw_item))

    @staticmethod
    def _fork_outputs_for_loop_iteration(
        baseline: Dict[str, NodeOutputUnion],
        body_ids: set[str],
        node_id: str,
        item_out: NodeOutputUnion,
    ) -> Dict[str, NodeOutputUnion]:
        out: Dict[str, NodeOutputUnion] = {}
        for k, v in baseline.items():
            if k in body_ids or k == node_id:
                continue
            out[k] = v
        out[node_id] = item_out
        return out

    @staticmethod
    def _patch_last_for_loop_body_node_result(
        node_results: list[NodeRunResult],
        *,
        node_id: str,
        body_node_id: str,
        merged_output: NodeOutputUnion,
    ) -> None:
        """After parallel For Loop iterations, align the last body node run with merged output (sequential parity)."""
        matches = [
            i
            for i, r in enumerate(node_results)
            if r.node_id == body_node_id and (r.details or {}).get("for_loop_node_id") == node_id
        ]
        if not matches:
            return
        last_i = max(
            matches,
            key=lambda i: float(sn) if (sn := node_results[i].step_number) is not None else float("-inf"),
        )
        prev = node_results[last_i]
        node_results[last_i] = NodeRunResult(
            node_id=prev.node_id,
            status=prev.status,
            output=merged_output,
            error=prev.error,
            latency_ms=prev.latency_ms,
            details=prev.details,
            step_number=prev.step_number,
        )

    def _try_catch_structured_error_payload(
        self,
        *,
        failed_node_id: str,
        failed_node: Any,
        message: str,
        error_type: str = "node_execution_error",
        extra_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ctype: Any = None
        if isinstance(failed_node, dict):
            ctype = failed_node.get("control_type") or failed_node.get("primitive_type") or failed_node.get("skill_type")
        else:
            ctype = getattr(failed_node, "control_type", None) or getattr(failed_node, "primitive_type", None)
            if ctype is None and isinstance(getattr(failed_node, "data", None), dict):
                data = getattr(failed_node, "data") or {}
                ctype = data.get("control_type") or data.get("primitive_type") or data.get("skill_type")
        return {
            "node_id": failed_node_id,
            "node_type": str(ctype or type(failed_node).__name__),
            "message": str(message),
            "error_type": error_type,
            "details": dict(extra_details or {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _resolve_try_catch_value_edge(
        self, tc_id: str, edges: List[GraphEdge], outputs: Dict[str, NodeOutputUnion]
    ) -> Any:
        for e in edges:
            if e.target != tc_id:
                continue
            if (e.target_handle or "") != "value":
                continue
            out = outputs.get(e.source)
            if out is None:
                continue
            slot = _get_slot_value(out, e.source_handle)
            return node_output_to_input_override_value(slot)
        return None

    async def _run_try_catch_region_waves(
        self,
        tc_id: str,
        body_ids: set[str],
        phase: Literal["try", "catch"],
        edges: List[GraphEdge],
        nodes_by_id: Dict[str, Any],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Optional[Dict[str, Any]],
        workflow: WorkflowDefinition,
        stack: frozenset,
        recorder: Any,
        node_results: list[NodeRunResult],
        stream_run_id: Optional[uuid.UUID] = None,
        stream_evt_acc: Optional[list[tuple[str, dict[str, Any]]]] = None,
        execution_time_zone: Optional[str] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        parallel_side_effects_lock: Optional[threading.Lock] = None,
        halt_on_first_error: bool = False,
        *,
        seed_handle: str,
    ) -> tuple[bool, Optional[dict[str, Any]]]:
        """Run a Try/Catch branch subgraph. Returns (ok, failure_snapshot)."""
        with self._transcribe_stream_sink(stream_evt_acc):
            plock = parallel_side_effects_lock
            inner_edges = [e for e in edges if e.source in body_ids and e.target in body_ids]
            in_degree, adjacency = _build_in_degree_and_adjacency(sorted(body_ids), inner_edges, nodes_by_id)
            seed_counts: Dict[str, int] = {}
            for e in edges:
                if (
                    e.source == tc_id
                    and e.target in body_ids
                    and (e.source_handle or "") == seed_handle
                ):
                    seed_counts[e.target] = seed_counts.get(e.target, 0) + 1
            for _t, c in seed_counts.items():
                in_degree[_t] += c
            for _t, c in seed_counts.items():
                in_degree[_t] -= c

            ready = deque[str](nid for nid in body_ids if in_degree[nid] == 0)
            order = _topological_order(sorted(body_ids), inner_edges)
            order_index = {nid: i for i, nid in enumerate(order)}
            ov = input_overrides or {}
            om = output_overrides_map or {}
            wave_cap = self._wave_cap_for_run()
            failure_snapshot: Optional[dict[str, Any]] = None

            while ready:
                batch = pop_wave_batch(ready, order_index, wave_cap)
                batch = split_batch_isolating_audio_steps(batch, ready, order_index, nodes_by_id)

                batch_failed_early = False
                if stream_evt_acc is not None:
                    with contextlib.nullcontext() if plock is None else plock:
                        for nid in batch:
                            stream_evt_acc.append(("node.started", {"node_id": nid}))

                async def run_body_node_tc(node_inner: str):
                    bn = nodes_by_id[node_inner]
                    t0 = time.monotonic()
                    if isinstance(bn, ForLoopControlNode):
                        r_inner = await self._run_for_loop_node(
                            node_inner,
                            bn,
                            edges,
                            outputs,
                            ov,
                            workflow,
                            stack,
                            nodes_by_id,
                            recorder,
                            node_results,
                            stream_run_id,
                            stream_evt_acc,
                            execution_time_zone=execution_time_zone,
                            output_overrides_map=om,
                            parallel_side_effects_lock=plock,
                        )
                    elif isinstance(bn, TryCatchControlNode):
                        r_inner = await self._run_try_catch_node(
                            node_inner,
                            bn,
                            edges,
                            outputs,
                            ov,
                            workflow,
                            stack,
                            nodes_by_id,
                            recorder,
                            node_results,
                            stream_run_id,
                            stream_evt_acc,
                            execution_time_zone=execution_time_zone,
                            output_overrides_map=om,
                            parallel_side_effects_lock=plock,
                        )
                    else:
                        upstream = _resolve_upstream_for_node(node_inner, edges, outputs)
                        r_inner = await self._execute_node(
                            node_inner,
                            bn,
                            upstream,
                            edges,
                            outputs,
                            ov,
                            workflow=workflow,
                            execution_stack=stack,
                            execution_time_zone=execution_time_zone,
                            loop_list_carry=None,
                            for_loop_id=None,
                            output_overrides_map=om,
                            stream_run_id=stream_run_id,
                            for_loop_iteration=None,
                        )
                    elapsed_inner = (time.monotonic() - t0) * 1000
                    return r_inner, elapsed_inner

                gathered_tc = await asyncio.gather(
                    *[run_body_node_tc(nid) for nid in batch],
                    return_exceptions=True,
                )

                for node_inner, raw in zip(batch, gathered_tc):
                    if isinstance(raw, BaseException):
                        result = {"status": "error", "error": _format_exception(raw)}
                        elapsed_ms = 0.0
                    else:
                        result, elapsed_ms = cast(tuple[dict[str, Any], float], raw)

                    det_raw: Any = result.get("details") or {}
                    det_inner: dict[str, Any] = dict(det_raw if isinstance(det_raw, dict) else {})
                    det_inner["try_catch_phase"] = phase
                    det_inner["try_catch_anchor_id"] = tc_id

                    if halt_on_first_error and phase == "try" and result["status"] != "ok":
                        det_inner["handled_by_try_catch"] = tc_id

                    out_for_log_tc: Any = result.get("output")
                    raw_output_tc: dict[str, Any] | None = None
                    if out_for_log_tc is not None:
                        md_tc = getattr(out_for_log_tc, "model_dump", None)
                        if callable(md_tc):
                            raw_output_tc = md_tc(mode="json")
                    details_for_client_tc = merge_details_with_output_explorer(det_inner, raw_output_tc)

                    with contextlib.nullcontext() if plock is None else plock:
                        node_run_inner = NodeRunResult(
                            node_id=node_inner,
                            status=result["status"],
                            output=result.get("output"),
                            error=result.get("error"),
                            latency_ms=round(elapsed_ms, 2),
                            details=details_for_client_tc,
                            step_number=recorder.next_step(),
                        )
                        node_results.append(node_run_inner)
                        self.bump_node_execution_budget_after_step()

                        if stream_evt_acc is not None:
                            evn_tc = "node.completed" if result["status"] == "ok" else "node.failed"
                            payload_tc: dict[str, Any] = {
                                "node_id": node_inner,
                                "result": node_run_inner.model_dump(mode="json"),
                            }
                            if halt_on_first_error and phase == "try" and result["status"] != "ok":
                                payload_tc["handled_by_try_catch"] = tc_id
                            stream_evt_acc.append((evn_tc, payload_tc))

                        if stream_run_id is not None:
                            safe_out_tc, safe_det_tc = redact_node_log_for_storage(
                                raw_output_tc, cast(dict[str, Any], det_inner)
                            )
                            safe_det_tc = attach_output_explorer_after_redact(safe_out_tc, safe_det_tc)
                            self.session.add(
                                NodeRunLog(
                                    run_id=stream_run_id,
                                    node_id=node_inner,
                                    step_number=node_run_inner.step_number,
                                    status=result["status"],
                                    output_data=safe_out_tc,
                                    error=result.get("error"),
                                    latency_ms=round(elapsed_ms, 2),
                                    details=safe_det_tc,
                                )
                            )
                            self.session.commit()

                    if result["status"] != "ok":
                        batch_failed_early = True
                        if failure_snapshot is None:
                            failure_snapshot = {
                                "node_id": node_inner,
                                "message": result.get("error") or "error",
                                "result": dict(result),
                            }

                    if result["status"] == "ok" and result.get("output"):
                        outputs[node_inner] = cast(NodeOutputUnion, result["output"])

                    node_exec_inner: Any = nodes_by_id[node_inner]
                    output_val_inner: Any = result.get("output")
                    if isinstance(
                        node_exec_inner,
                        (
                            BasicConditionalControlNode,
                            BetweenControlNode,
                            IsControlNode,
                            IsEmptyControlNode,
                            GtControlNode,
                            LtControlNode,
                            GteControlNode,
                            LteControlNode,
                        ),
                    ) and isinstance(output_val_inner, ConditionalNodeOutput):
                        for edge in inner_edges:
                            if edge.source == node_inner and edge.source_handle == output_val_inner.branch:
                                succ = edge.target
                                if succ in body_ids:
                                    in_degree[succ] -= 1
                                    if in_degree[succ] == 0:
                                        ready.append(succ)
                        _executor_mod()._decrement_signal_out_triggers(
                            node_inner,
                            inner_edges,
                            body_ids,
                            in_degree,
                            ready,
                        )
                    else:
                        for succ in adjacency.get(node_inner, []):
                            if succ not in body_ids:
                                continue
                            in_degree[succ] -= 1
                            if in_degree[succ] == 0:
                                ready.append(succ)

                    if halt_on_first_error and result["status"] != "ok":
                        break

                if halt_on_first_error and batch_failed_early:
                    ready.clear()

            return failure_snapshot is None, failure_snapshot

    async def _run_try_catch_node(
        self,
        node_id: str,
        node: TryCatchControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Optional[Dict[str, Any]],
        workflow: WorkflowDefinition,
        stack: frozenset,
        nodes_by_id: Dict[str, Any],
        recorder: Any,
        node_results: list[NodeRunResult],
        stream_run_id: Optional[uuid.UUID] = None,
        stream_evt_acc: Optional[list[tuple[str, dict[str, Any]]]] = None,
        execution_time_zone: Optional[str] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        parallel_side_effects_lock: Optional[threading.Lock] = None,
    ) -> Dict[str, Any]:
        ov = input_overrides or {}
        om = output_overrides_map or {}
        if node_id in om:
            forced = om[node_id]
            outputs[node_id] = forced
            return {
                "status": "ok",
                "output": forced,
                "details": {"resolved_inputs": {}, "forced_output": True},
                "try_catch_branch": "try",
            }

        try_body = try_catch_try_region(node_id, edges)
        catch_body = try_catch_catch_region(node_id, edges)
        catch_seeds = try_catch_catch_seeds(node_id, edges)
        ok_try, snap = await self._run_try_catch_region_waves(
            node_id,
            try_body,
            "try",
            edges,
            nodes_by_id,
            outputs,
            ov,
            workflow,
            stack,
            recorder,
            node_results,
            stream_run_id,
            stream_evt_acc,
            execution_time_zone=execution_time_zone,
            output_overrides_map=om,
            parallel_side_effects_lock=parallel_side_effects_lock,
            halt_on_first_error=True,
            seed_handle="try",
        )
        if ok_try:
            payload_val = self._resolve_try_catch_value_edge(node_id, edges, outputs)
            data_ok: dict[str, Any] = {"ok": True, "value": payload_val}
            out_ok = DictionaryNodeOutput(node_id=node_id, data=data_ok)
            outputs[node_id] = out_ok
            return {
                "status": "ok",
                "output": out_ok,
                "details": {"resolved_inputs": {"phase": "try_ok"}},
                "try_catch_branch": "try",
            }

        fail_id = str((snap or {}).get("node_id") or "?")
        fail_node = nodes_by_id.get(fail_id)
        msg = str((snap or {}).get("message") or "try region failed")
        err_blob = self._try_catch_structured_error_payload(
            failed_node_id=fail_id,
            failed_node=fail_node if fail_node is not None else {},
            message=msg,
            extra_details={"raw_result": (snap or {}).get("result") if isinstance((snap or {}).get("result"), dict) else {}},
        )
        data_fail: dict[str, Any] = {"ok": False, "error": err_blob}

        if not catch_seeds:
            return {
                "status": "error",
                "error": msg,
                "details": {"try_catch": data_fail},
            }

        out_fail_pre = DictionaryNodeOutput(node_id=node_id, data=data_fail)
        outputs[node_id] = out_fail_pre
        await self._run_try_catch_region_waves(
            node_id,
            catch_body,
            "catch",
            edges,
            nodes_by_id,
            outputs,
            ov,
            workflow,
            stack,
            recorder,
            node_results,
            stream_run_id,
            stream_evt_acc,
            execution_time_zone=execution_time_zone,
            output_overrides_map=om,
            parallel_side_effects_lock=parallel_side_effects_lock,
            halt_on_first_error=False,
            seed_handle="catch",
        )
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node_id, data=dict(data_fail)),
            "details": {"resolved_inputs": {"phase": "catch_run"}},
            "try_catch_branch": "catch",
        }

    async def _run_loop_body_waves(
        self,
        for_loop_id: str,
        body_ids: set[str],
        iteration_index: int,
        edges: List[GraphEdge],
        nodes_by_id: Dict[str, Any],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Optional[Dict[str, Any]],
        workflow: WorkflowDefinition,
        stack: frozenset,
        recorder: Any,
        node_results: list[NodeRunResult],
        stream_run_id: Optional[uuid.UUID] = None,
        stream_evt_acc: Optional[list[tuple[str, dict[str, Any]]]] = None,
        execution_time_zone: Optional[str] = None,
        loop_list_carry: Optional[Dict[tuple[str, str], list[Any]]] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        parallel_side_effects_lock: Optional[threading.Lock] = None,
    ) -> None:
        with self._transcribe_stream_sink(stream_evt_acc):
            plock = parallel_side_effects_lock
            inner_edges = [e for e in edges if e.source in body_ids and e.target in body_ids]
            in_degree, adjacency = _build_in_degree_and_adjacency(sorted(body_ids), inner_edges, nodes_by_id)
            fl_counts: Dict[str, int] = {}
            for e in edges:
                if e.source == for_loop_id and e.target in body_ids:
                    fl_counts[e.target] = fl_counts.get(e.target, 0) + 1
            for _t, c in fl_counts.items():
                in_degree[_t] += c
            for _t, c in fl_counts.items():
                in_degree[_t] -= c

            ready: deque[str] = deque(nid for nid in body_ids if in_degree[nid] == 0)
            order = _topological_order(sorted(body_ids), inner_edges)
            order_index = {nid: i for i, nid in enumerate(order)}
            ov = input_overrides or {}
            om = output_overrides_map or {}
            wave_cap = self._wave_cap_for_run()

            while ready:
                batch = pop_wave_batch(ready, order_index, wave_cap)
                batch = split_batch_isolating_audio_steps(batch, ready, order_index, nodes_by_id)

                if stream_evt_acc is not None:
                    with contextlib.nullcontext() if plock is None else plock:
                        for nid in batch:
                            stream_evt_acc.append(("node.started", {"node_id": nid}))

                async def run_body_node(node_id: str):
                    node = nodes_by_id[node_id]
                    t0 = time.monotonic()
                    if isinstance(node, ForLoopControlNode):
                        r = await self._run_for_loop_node(
                            node_id,
                            node,
                            edges,
                            outputs,
                            ov,
                            workflow,
                            stack,
                            nodes_by_id,
                            recorder,
                            node_results,
                            stream_run_id,
                            stream_evt_acc,
                            execution_time_zone=execution_time_zone,
                            output_overrides_map=om,
                            parallel_side_effects_lock=plock,
                        )
                    elif isinstance(node, TryCatchControlNode):
                        r = await self._run_try_catch_node(
                            node_id,
                            node,
                            edges,
                            outputs,
                            ov,
                            workflow,
                            stack,
                            nodes_by_id,
                            recorder,
                            node_results,
                            stream_run_id,
                            stream_evt_acc,
                            execution_time_zone=execution_time_zone,
                            output_overrides_map=om,
                            parallel_side_effects_lock=plock,
                        )
                    else:
                        upstream = _resolve_upstream_for_node(node_id, edges, outputs)
                        r = await self._execute_node(
                            node_id,
                            node,
                            upstream,
                            edges,
                            outputs,
                            ov,
                            workflow=workflow,
                            execution_stack=stack,
                            execution_time_zone=execution_time_zone,
                            loop_list_carry=loop_list_carry,
                            for_loop_id=for_loop_id,
                            output_overrides_map=om,
                            stream_run_id=stream_run_id,
                            for_loop_iteration=iteration_index,
                        )
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    return r, elapsed_ms

                gathered = await asyncio.gather(
                    *[run_body_node(nid) for nid in batch],
                    return_exceptions=True,
                )

                for node_id, raw in zip(batch, gathered):
                    if isinstance(raw, BaseException):
                        result = {"status": "error", "error": _format_exception(raw)}
                        elapsed_ms = 0.0
                    else:
                        result, elapsed_ms = cast(tuple[dict[str, Any], float], raw)

                    det_raw: Any = result.get("details") or {}
                    det: dict[str, Any] = dict(det_raw if isinstance(det_raw, dict) else {})
                    det["for_loop_node_id"] = for_loop_id
                    det["for_loop_iteration"] = iteration_index

                    out_for_log_fl: Any = result.get("output")
                    raw_output_fl: dict[str, Any] | None = None
                    if out_for_log_fl is not None:
                        md_fl = getattr(out_for_log_fl, "model_dump", None)
                        if callable(md_fl):
                            raw_output_fl = md_fl(mode="json")
                    details_for_client_fl = merge_details_with_output_explorer(det, raw_output_fl)

                    with contextlib.nullcontext() if plock is None else plock:
                        node_run_result = NodeRunResult(
                            node_id=node_id,
                            status=result["status"],
                            output=result.get("output"),
                            error=result.get("error"),
                            latency_ms=round(elapsed_ms, 2),
                            details=details_for_client_fl,
                            step_number=recorder.next_step(),
                        )
                        node_results.append(node_run_result)
                        self.bump_node_execution_budget_after_step()

                        if stream_evt_acc is not None:
                            evn = "node.completed" if result["status"] == "ok" else "node.failed"
                            stream_evt_acc.append(
                                (
                                    evn,
                                    {
                                        "node_id": node_id,
                                        "result": node_run_result.model_dump(mode="json"),
                                    },
                                )
                            )

                        if stream_run_id is not None:
                            safe_out, safe_det = redact_node_log_for_storage(raw_output_fl, cast(dict[str, Any], det))
                            safe_det = attach_output_explorer_after_redact(safe_out, safe_det)
                            self.session.add(
                                NodeRunLog(
                                    run_id=stream_run_id,
                                    node_id=node_id,
                                    step_number=node_run_result.step_number,
                                    status=result["status"],
                                    output_data=safe_out,
                                    error=result.get("error"),
                                    latency_ms=round(elapsed_ms, 2),
                                    details=safe_det,
                                )
                            )
                            self.session.commit()

                    if result["status"] == "ok" and result.get("output"):
                        outputs[node_id] = cast(NodeOutputUnion, result["output"])

                    node_exec: Any = nodes_by_id[node_id]
                    output_val: Any = result.get("output")
                    if isinstance(
                        node_exec,
                        (
                            BasicConditionalControlNode,
                            BetweenControlNode,
                            IsControlNode,
                            IsEmptyControlNode,
                            GtControlNode,
                            LtControlNode,
                            GteControlNode,
                            LteControlNode,
                        ),
                    ) and isinstance(output_val, ConditionalNodeOutput):
                        for edge in inner_edges:
                            if edge.source == node_id and edge.source_handle == output_val.branch:
                                succ = edge.target
                                if succ in body_ids:
                                    in_degree[succ] -= 1
                                    if in_degree[succ] == 0:
                                        ready.append(succ)
                        _executor_mod()._decrement_signal_out_triggers(node_id, inner_edges, body_ids, in_degree, ready)
                    else:
                        for succ in adjacency.get(node_id, []):
                            if succ not in body_ids:
                                continue
                            in_degree[succ] -= 1
                            if in_degree[succ] == 0:
                                ready.append(succ)

    async def _run_for_loop_node(
        self,
        node_id: str,
        node: ForLoopControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Optional[Dict[str, Any]],
        workflow: WorkflowDefinition,
        stack: frozenset,
        nodes_by_id: Dict[str, Any],
        recorder: Any,
        node_results: list[NodeRunResult],
        stream_run_id: Optional[uuid.UUID] = None,
        stream_evt_acc: Optional[list[tuple[str, dict[str, Any]]]] = None,
        execution_time_zone: Optional[str] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        parallel_side_effects_lock: Optional[threading.Lock] = None,
    ) -> Dict[str, Any]:
        _ = stream_run_id
        ov = input_overrides or {}
        om = output_overrides_map or {}
        if node_id in om:
            forced = om[node_id]
            outputs[node_id] = forced
            return {
                "status": "ok",
                "output": forced,
                "details": {"resolved_inputs": {}, "forced_output": True},
            }

        body_ids = for_loop_body_node_ids(node_id, edges, nodes_by_id)
        items = list(self._resolve_for_loop_list(node, edges, outputs, ov))
        items = self._slice_for_loop_max_iterations_node(node, items)

        end_nid = _executor_mod()._paired_for_loop_end_id(node_id, nodes_by_id)
        if end_nid and end_nid in om:
            items = []

        limits = getattr(self, "_resolved_execution_limits", None)
        if limits is not None and items and len(items) > limits.max_loop_iterations:
            return {
                "status": "error",
                "error": (
                    f"For Loop list length ({len(items)}) exceeds maximum iterations "
                    f"({limits.max_loop_iterations}) allowed for this run."
                ),
                "details": {"resolved_inputs": {"list_length": len(items), "limit": limits.max_loop_iterations}},
            }

        n_items = len(items)
        mode = self._for_loop_iteration_mode(node)
        cot = self._for_loop_continue_on_error(node)
        use_parallel_outer = mode in ("parallel", "batched") and not cot

        results_track: list[Any | None] = [None] * n_items
        errors_track: list[dict[str, Any]] = []

        if not items:
            self._for_loop_record_summary(node_id, processed=0, results_track=[], errors_track=[])
            outputs[node_id] = ListNodeOutput(node_id=node_id, data=[])
            return {
                "status": "ok",
                "output": ListNodeOutput(node_id=node_id, data=[]),
                "details": {"resolved_inputs": {"input_list": [], "iteration_count": 0}},
            }

        def record_iteration_failure(i_iter: int, msg: str) -> dict[str, Any] | None:
            results_track[i_iter] = None
            errors_track.append({"iteration": i_iter, "message": msg})
            if cot:
                return None
            return {
                "status": "error",
                "error": msg,
                "details": {"for_loop_iteration": i_iter},
            }

        if use_parallel_outer:
            baseline: Dict[str, NodeOutputUnion] = {
                k: v for k, v in outputs.items() if k not in body_ids and k != node_id
            }
            iter_lock = threading.Lock()
            last_out_item = self._item_json_to_node_output(node_id, items[-1])
            chunk_sz = self._for_loop_parallel_chunk_size(node, mode)
            merged_carry: Dict[tuple[str, str], list[Any]] = {}
            fatal: dict[str, Any] | None = None

            async def run_one_iteration(
                i: int,
                raw_item: Any,
            ) -> tuple[int, Dict[str, NodeOutputUnion], Dict[tuple[str, str], list[Any]], bool, str]:
                item_out = self._item_json_to_node_output(node_id, raw_item)
                scratch = self._fork_outputs_for_loop_iteration(baseline, body_ids, node_id, item_out)
                carry: Dict[tuple[str, str], list[Any]] = {}
                before_ct = len(node_results)
                await self._run_loop_body_waves(
                    node_id,
                    body_ids,
                    i,
                    edges,
                    nodes_by_id,
                    scratch,
                    ov,
                    workflow,
                    stack,
                    recorder,
                    node_results,
                    stream_run_id,
                    stream_evt_acc,
                    execution_time_zone=execution_time_zone,
                    loop_list_carry=carry,
                    output_overrides_map=om,
                    parallel_side_effects_lock=iter_lock,
                )
                chunk_res = node_results[before_ct:]
                bad = [r for r in chunk_res if r.status != "ok"]
                ok_i = not bad
                err_m = "" if ok_i else str(bad[0].error or "error")
                return i, scratch, carry, ok_i, err_m

            scratch_final: Dict[str, NodeOutputUnion] = {}

            stop_parallel = False
            for chunk_start in range(0, n_items, chunk_sz):
                chunk = await asyncio.gather(
                    *[run_one_iteration(i, items[i]) for i in range(chunk_start, min(chunk_start + chunk_sz, n_items))],
                    return_exceptions=True,
                )
                for j, raw_chunk in enumerate(chunk):
                    idx = chunk_start + j
                    if isinstance(raw_chunk, BaseException):
                        fatal = record_iteration_failure(idx, _format_exception(raw_chunk)) or {
                            "status": "error",
                            "error": _format_exception(raw_chunk),
                            "details": {"for_loop_iteration": idx},
                        }
                        stop_parallel = True
                        break

                    sub_i, scratch_i, carry_i, ok_i, err_msg = cast(
                        tuple[int, Dict[str, NodeOutputUnion], Dict[tuple[str, str], list[Any]], bool, str],
                        raw_chunk,
                    )

                    for ck, lst in carry_i.items():
                        merged_carry.setdefault(ck, []).extend(lst)

                    if not ok_i:
                        fatal_resp = record_iteration_failure(sub_i, err_msg or "error") or {
                            "status": "error",
                            "error": err_msg or "error",
                            "details": {"for_loop_iteration": sub_i},
                        }
                        fatal = fatal_resp
                        stop_parallel = True
                        break

                    results_track[sub_i] = self._for_loop_iteration_item_primitive(node_id, items[sub_i])
                    scratch_final = scratch_i

                if stop_parallel:
                    break

            if fatal is not None:
                self._for_loop_record_summary(node_id, processed=n_items, results_track=results_track, errors_track=errors_track)
                return fatal

            for bid in body_ids:
                bn = nodes_by_id.get(bid)
                if isinstance(bn, AddToListUtilityNode):
                    ck = (node_id, bid)
                    lst = list(merged_carry.get(ck, []))
                    merged_out = ListNodeOutput(node_id=bid, data=lst)
                    outputs[bid] = merged_out
                    self._patch_last_for_loop_body_node_result(
                        node_results,
                        node_id=node_id,
                        body_node_id=bid,
                        merged_output=merged_out,
                    )

            for bid in body_ids:
                if isinstance(nodes_by_id.get(bid), AddToListUtilityNode):
                    continue
                if bid in scratch_final:
                    outputs[bid] = scratch_final[bid]

            outputs[node_id] = last_out_item
            self._for_loop_record_summary(node_id, processed=n_items, results_track=results_track, errors_track=errors_track)

            return {
                "status": "ok",
                "output": last_out_item,
                "details": {
                    "resolved_inputs": {
                        "input_list": items,
                        "iteration_count": len(items),
                        "iteration_mode": mode,
                    }
                },
            }

        loop_list_carry: Dict[tuple[str, str], list[Any]] = {}
        last_out = ListNodeOutput(node_id=node_id, data=[])
        fatal: dict[str, Any] | None = None

        for i, raw_item in enumerate(items):
            item_out = self._item_json_to_node_output(node_id, raw_item)
            outputs[node_id] = item_out
            last_out = item_out
            before_ct = len(node_results)

            for bid in body_ids:
                outputs.pop(bid, None)

            await self._run_loop_body_waves(
                node_id,
                body_ids,
                i,
                edges,
                nodes_by_id,
                outputs,
                ov,
                workflow,
                stack,
                recorder,
                node_results,
                stream_run_id,
                stream_evt_acc,
                execution_time_zone=execution_time_zone,
                loop_list_carry=loop_list_carry,
                output_overrides_map=om,
                parallel_side_effects_lock=parallel_side_effects_lock,
            )

            bad = [r for r in node_results[before_ct:] if r.status != "ok"]
            if bad:
                resp = record_iteration_failure(i, str(bad[0].error or "error"))
                if resp is not None:
                    fatal = resp
                    break
                continue

            results_track[i] = self._for_loop_iteration_item_primitive(node_id, raw_item)

        if fatal is not None:
            self._for_loop_record_summary(node_id, processed=n_items, results_track=results_track, errors_track=errors_track)
            return fatal

        for bid in body_ids:
            bn = nodes_by_id.get(bid)
            if isinstance(bn, AddToListUtilityNode):
                ck = (node_id, bid)
                lst = list(loop_list_carry.get(ck, []))
                outputs[bid] = ListNodeOutput(node_id=bid, data=lst)

        outputs[node_id] = last_out
        self._for_loop_record_summary(node_id, processed=n_items, results_track=results_track, errors_track=errors_track)
        return {
            "status": "ok",
            "output": last_out,
            "details": {
                "resolved_inputs": {
                    "input_list": items,
                    "iteration_count": len(items),
                    "iteration_mode": mode,
                    "continue_on_error": cot,
                }
            },
        }

    def _resolve_for_loop_end_node(
        self,
        node_id: str,
        node: ForLoopEndControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        *,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
    ) -> Dict[str, Any]:
        """Aggregate named exports from the paired For Loop body into one dictionary output."""
        om = output_overrides_map or {}
        if node_id in om:
            forced = om[node_id]
            return {
                "status": "ok",
                "output": forced,
                "details": {
                    "resolved_inputs": {
                        "exports": dict(forced.data) if isinstance(forced, DictionaryNodeOutput) else {}
                    },
                    "forced_output": True,
                },
            }
        export_edges = [e for e in edges if e.target == node_id and (e.target_handle or "") != "trigger"]
        data: dict[str, Any] = {}
        for e in sorted(export_edges, key=lambda x: (x.target_handle or "", x.source)):
            key = (e.target_handle or "").strip()
            out = outputs.get(e.source)
            if out is None:
                data[key] = None
            else:
                slot = _get_slot_value(out, e.source_handle)
                data[key] = node_output_to_input_override_value(slot)
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node_id, data=data),
            "details": {"resolved_inputs": {"exports": data}},
        }

    async def _execute_node(
        self,
        node_id: str,
        node: Any,
        upstream: list[NodeOutputUnion],
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Optional[Dict[str, Any]] = None,
        workflow: Optional[WorkflowDefinition] = None,
        execution_stack: Optional[frozenset] = None,
        execution_time_zone: Optional[str] = None,
        loop_list_carry: Optional[Dict[tuple[str, str], list[Any]]] = None,
        for_loop_id: Optional[str] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        stream_run_id: Optional[uuid.UUID] = None,
        for_loop_iteration: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Dispatch to the correct handler based on node kind."""
        om = output_overrides_map or {}
        if node_id in om:
            forced = om[node_id]
            return {
                "status": "ok",
                "output": forced,
                "details": {"resolved_inputs": {}, "forced_output": True},
            }
        async with self._node_execution_scope(node):
            ctx = ExecutionNodeContext(
                node_id=node_id,
                node=node,
                upstream=upstream,
                edges=edges,
                outputs=outputs,
                input_overrides=input_overrides,
                workflow=workflow,
                execution_stack=execution_stack,
                execution_time_zone=execution_time_zone,
                loop_list_carry=loop_list_carry,
                for_loop_id=for_loop_id,
                output_overrides_map=output_overrides_map,
                stream_run_id=stream_run_id,
                for_loop_iteration=for_loop_iteration,
            )
            return await dispatch_execute_node(self, ctx)

    # ------------------------------------------------------------------
    # Node handlers
    # ------------------------------------------------------------------

    def _resolve_decision_action_primitive_node(
        self, node: DecisionActionPrimitiveNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Emit a validated ``DecisionAction`` string as ``StringNodeOutput`` (for ``sandbox_decision_intent``)."""
        if upstream:
            first = upstream[0]
            t = _executor_mod()._text_from_stringish_output(first)
            if t is None and hasattr(first, "text"):
                t = getattr(first, "text", None)
            if t is None:
                return _executor_mod()._error_with_resolved_inputs(
                    "decision_action primitive: upstream must be string-like",
                    {"from_upstream": True},
                )
            s = str(t).strip()
            if s not in DECISION_ACTION_STRINGS:
                return _executor_mod()._error_with_resolved_inputs(
                    f"decision_action primitive: invalid action {s!r} (expected one of {sorted(DECISION_ACTION_STRINGS)})",
                    {"action": s},
                )
            return {
                "status": "ok",
                "output": StringNodeOutput(node_id=node.id, text=s),
                "details": {"resolved_inputs": {"action": s}},
            }
        raw = node.data.get("action", "wander")
        s = str(raw).strip() if raw is not None else ""
        if s not in DECISION_ACTION_STRINGS:
            return _executor_mod()._error_with_resolved_inputs(
                f"decision_action primitive: invalid action in node data {raw!r}",
                {"action": raw},
            )
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=s),
            "details": {"resolved_inputs": {"action": s}},
        }

    def _resolve_sandbox_tick_primitive_node(
        self,
        node: SandboxTickPrimitiveNode,
        upstream: list[NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Emit validated ``SandboxTickInput`` as ``DictionaryNodeOutput`` (run overrides, else wired tick)."""
        raw: dict | None = None
        ov = input_overrides.get("sandbox_tick")
        if isinstance(ov, dict) and "world" in ov and "pet" in ov and "tick" in ov:
            raw = dict(ov)
        if raw is None:
            raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                (
                    "sandbox_tick primitive: no tick — run from Sandbox (tick override), "
                    "or wire Start's sandbox_tick / a tick-shaped dictionary to input"
                ),
                {"sandbox_tick": None},
            )
        try:
            tick_in = SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_tick primitive: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        data = tick_in.model_dump(mode="json")
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"sandbox_tick": data}},
        }

    def _resolve_string_primitive_node(
        self, node: StringPrimitiveNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return the static string, or aggregate upstream text. When upstream exists,
        also include the node's own text so that String nodes with both incoming edges
        and user-entered content pass that content through."""
        if upstream:
            parts = []
            for out in upstream:
                if hasattr(out, "text"):
                    parts.append(out.text)
                elif hasattr(out, "data"):
                    parts.append(json.dumps(out.data))
            node_text = node.data.get("text", "").strip()
            if node_text:
                parts.append(node_text)
            text = "\n\n".join(parts)
        else:
            text = node.data.get("text", "")
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=text),
            "details": {"resolved_inputs": {"text": text}},
        }

    def _resolve_list_primitive_node(self, node: ListPrimitiveNode, upstream: list[NodeOutputUnion]) -> Dict[str, Any]:
        """Return the static list, or use upstream list (pass-through), or gather upstream outputs into a list."""
        if upstream:
            if len(upstream) == 1:
                out = upstream[0]
                if isinstance(out, ListNodeOutput):
                    return {
                        "status": "ok",
                        "output": ListNodeOutput(node_id=node.id, data=out.data),
                        "details": {"resolved_inputs": {"list": out.data}},
                    }
                if isinstance(out, StringNodeOutput):
                    text = (out.text or "").strip()
                    if text.startswith("["):
                        try:
                            parsed = json.loads(text)
                            if isinstance(parsed, list):
                                return {
                                    "status": "ok",
                                    "output": ListNodeOutput(node_id=node.id, data=parsed),
                                    "details": {"resolved_inputs": {"list": parsed}},
                                }
                        except (json.JSONDecodeError, TypeError):
                            pass
                if isinstance(out, StartNodeOutput):
                    for val in out.outputs.values():
                        if isinstance(val, list):
                            return {
                                "status": "ok",
                                "output": ListNodeOutput(node_id=node.id, data=val),
                                "details": {"resolved_inputs": {"list": val}},
                            }
            data = []
            for out in upstream:
                if hasattr(out, "text"):
                    data.append(out.text)
                elif hasattr(out, "data"):
                    if isinstance(getattr(out, "data"), list):
                        data.extend(getattr(out, "data"))
                    else:
                        data.append(getattr(out, "data"))
                elif hasattr(out, "value"):
                    data.append(out.value)
                else:
                    data.append(str(out))
        else:
            data = node.data if isinstance(node.data, list) else (node.data or [])
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"list": data}},
        }

    def _resolve_dictionary_primitive_node(
        self,
        node: DictionaryPrimitiveNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
    ) -> Dict[str, Any]:
        """Return the static dictionary, or merge upstream dictionaries and keyed scalars.

        For each non-trigger incoming edge, merge ``DictionaryNodeOutput.data`` with
        ``dict.update``. For any other resolved output (e.g. int/string from Start slots),
        set ``data[source_handle]`` to the plain Python value (``source_handle`` is the
        Start slot key when wiring from Start). Empty ``source_handle`` uses ``\"output\"``.
        If that key already exists (e.g. several parallel wires all use ``\"output\"``),
        the key is suffixed with ``_`` + source node id so each wire contributes a distinct entry.
        """
        data_edges = [e for e in edges if e.target == node.id and (e.target_handle or "") != "trigger"]
        if not data_edges:
            static_payload = dict(node.data) if isinstance(node.data, dict) else {}
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=static_payload),
                "details": {"resolved_inputs": {"data": static_payload}},
            }
        merged: dict[str, Any] = {}
        for edge in data_edges:
            src = edge.source
            out = outputs.get(src)
            if out is None:
                continue
            slot_val = _get_slot_value(out, edge.source_handle)
            if isinstance(slot_val, DictionaryNodeOutput):
                merged.update(dict(slot_val.data))
            else:
                base_key = (edge.source_handle or "").strip() or "output"
                key = base_key
                if key in merged:
                    key = f"{base_key}_{edge.source}"
                merged[key] = node_output_to_input_override_value(slot_val)
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=merged),
            "details": {"resolved_inputs": {"data": merged}},
        }

    def _resolve_boolean_primitive_node(
        self, node: BooleanPrimitiveNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return the static boolean, or first upstream boolean."""
        if upstream:
            first = upstream[0]
            if isinstance(first, BooleanNodeOutput):
                return {
                    "status": "ok",
                    "output": BooleanNodeOutput(node_id=node.id, value=first.value),
                    "details": {"resolved_inputs": {"value": first.value}},
                }
            if hasattr(first, "text"):
                s = (first.text or "").strip().lower()
                val = s in ("true", "yes", "1") if s else False
                return {
                    "status": "ok",
                    "output": BooleanNodeOutput(node_id=node.id, value=val),
                    "details": {"resolved_inputs": {"value": val}},
                }
        val = node.data.get("value", False)
        if not isinstance(val, bool):
            val = str(val).strip().lower() in ("true", "yes", "1")
        val = bool(val)
        return {
            "status": "ok",
            "output": BooleanNodeOutput(node_id=node.id, value=val),
            "details": {"resolved_inputs": {"value": val}},
        }

    def _resolve_int_primitive_node(self, node: IntPrimitiveNode, upstream: list[NodeOutputUnion]) -> Dict[str, Any]:
        """Return the static int, or first upstream int."""
        if upstream:
            first = upstream[0]
            if isinstance(first, IntNodeOutput):
                return {
                    "status": "ok",
                    "output": IntNodeOutput(node_id=node.id, value=first.value),
                    "details": {"resolved_inputs": {"value": first.value}},
                }
            if hasattr(first, "value") and isinstance(getattr(first, "value"), int):
                v = int(getattr(first, "value"))
                return {
                    "status": "ok",
                    "output": IntNodeOutput(node_id=node.id, value=v),
                    "details": {"resolved_inputs": {"value": v}},
                }
            try:
                if hasattr(first, "text"):
                    v = int(first.text or 0)
                    return {
                        "status": "ok",
                        "output": IntNodeOutput(node_id=node.id, value=v),
                        "details": {"resolved_inputs": {"value": v}},
                    }
            except (ValueError, TypeError):
                pass
        val = node.data.get("value", 0)
        try:
            val = int(val) if val is not None else 0
        except (ValueError, TypeError):
            val = 0
        return {
            "status": "ok",
            "output": IntNodeOutput(node_id=node.id, value=val),
            "details": {"resolved_inputs": {"value": val}},
        }

    def _resolve_datetime_primitive_node(
        self, node: DateTimePrimitiveNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return static RFC3339 iso from data, or first upstream datetime/string."""
        if upstream:
            first = upstream[0]
            if isinstance(first, DateTimeNodeOutput):
                return {
                    "status": "ok",
                    "output": DateTimeNodeOutput(node_id=node.id, iso=first.iso),
                    "details": {"resolved_inputs": {"iso": first.iso}},
                }
            if isinstance(first, StringNodeOutput):
                norm = parse_rfc3339_datetime_string(first.text)
                if norm is not None:
                    return {
                        "status": "ok",
                        "output": DateTimeNodeOutput(node_id=node.id, iso=norm),
                        "details": {"resolved_inputs": {"iso": norm}},
                    }
            t = _executor_mod()._text_from_stringish_output(first)
            if t is not None:
                norm = parse_rfc3339_datetime_string(t)
                if norm is not None:
                    return {
                        "status": "ok",
                        "output": DateTimeNodeOutput(node_id=node.id, iso=norm),
                        "details": {"resolved_inputs": {"iso": norm}},
                    }
        if bool((node.data or {}).get("use_now")):
            try:
                now_iso = utc_now_rfc3339_normalized_for_executor()
            except RuntimeError:
                return _executor_mod()._error_with_resolved_inputs(
                    "DateTime primitive: use_now could not normalize current UTC time.",
                    {"iso": None, "use_now": True},
                )
            return {
                "status": "ok",
                "output": DateTimeNodeOutput(node_id=node.id, iso=now_iso),
                "details": {"resolved_inputs": {"iso": now_iso, "use_now": True}},
            }
        raw = (node.data or {}).get("iso")
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "DateTime primitive: set a value in the editor or wire an upstream datetime/string.",
                {"iso": None},
            )
        norm = parse_rfc3339_datetime_string(str(raw))
        if norm is None:
            return _executor_mod()._error_with_resolved_inputs(
                "DateTime primitive: value is not a valid RFC3339 datetime.",
                {"iso": raw},
            )
        return {
            "status": "ok",
            "output": DateTimeNodeOutput(node_id=node.id, iso=norm),
            "details": {"resolved_inputs": {"iso": norm}},
        }

    def _resolve_list_to_string_node(
        self, node: ListToStringUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Convert upstream list input to string representation for passing to prompts."""
        data: List[Any] = []
        if upstream:
            first = upstream[0]
            if isinstance(first, ListNodeOutput):
                data = first.data
            elif isinstance(first, StartNodeOutput):
                # Start outputs dict; pick first list value or use []
                for val in first.outputs.values():
                    if isinstance(val, list):
                        data = val
                        break
            elif hasattr(first, "data") and isinstance(getattr(first, "data"), list):
                data = getattr(first, "data")
        cfg = node.data if isinstance(node.data, dict) else {}
        use_text_join = bool(cfg.get("use_text_join"))
        add_lb_raw = cfg.get("add_line_breaks_between_items")
        add_line_breaks = True if add_lb_raw is None else bool(add_lb_raw)
        if use_text_join:
            sep = "\n" if add_line_breaks else " "
            text = sep.join(_executor_mod()._list_item_to_join_token(x) for x in data)
            resolved = {
                "list": data,
                "use_text_join": True,
                "add_line_breaks_between_items": add_line_breaks,
            }
        else:
            text = json.dumps(data, indent=2) if isinstance(data, (list, dict)) else str(data)
            resolved = {
                "list": data,
                "use_text_join": False,
                "add_line_breaks_between_items": add_line_breaks,
            }
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=text),
            "details": {"resolved_inputs": resolved},
        }

    def _resolve_string_to_list_node(
        self, node: StringToListUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Parse JSON array text from upstream into a list output."""
        if not upstream:
            return _executor_mod()._error_with_resolved_inputs("String to List: no upstream input", {"upstream": False})
        first = upstream[0]
        t = _executor_mod()._text_from_stringish_output(first)
        if t is None:
            if hasattr(first, "text"):
                t = getattr(first, "text")
            else:
                return _executor_mod()._error_with_resolved_inputs(
                    "String to List: expected string-like upstream output (String, LLM response, or Start text)",
                    {"upstream_type": type(first).__name__},
                )
        text = (t or "").strip()
        if not text:
            return _executor_mod()._error_with_resolved_inputs("String to List: input text is empty", {"text_chars": 0})
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            return _executor_mod()._error_with_resolved_inputs(
                f"String to List: invalid JSON ({e})",
                {"text": text[:2048]},
            )
        if not isinstance(parsed, list):
            return _executor_mod()._error_with_resolved_inputs(
                "String to List: JSON must be an array",
                {"text": text[:2048]},
            )
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=parsed),
            "details": {"resolved_inputs": {"text": text}},
        }

    def _resolve_int_to_string_node(
        self, node: IntToStringUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Convert upstream int (or parseable string / Start int slot) to decimal string."""
        if not upstream:
            return _executor_mod()._error_with_resolved_inputs("Int to String: no upstream input", {"upstream": False})
        first = upstream[0]
        n: Optional[int] = None
        resolved_key: Optional[str] = None
        if isinstance(first, IntNodeOutput):
            n = first.value
        elif isinstance(first, BooleanNodeOutput):
            return _executor_mod()._error_with_resolved_inputs(
                "Int to String: boolean is not an integer",
                {"upstream_type": "BooleanNodeOutput"},
            )
        elif isinstance(first, StartNodeOutput):
            for key, val in first.outputs.items():
                if isinstance(val, bool):
                    continue
                if isinstance(val, int):
                    n = val
                    resolved_key = key
                    break
                parsed = parse_strict_int_for_slot(val, "input")
                if parsed[0] is not None:
                    n = parsed[0]
                    resolved_key = key
                    break
            if n is None:
                return _executor_mod()._error_with_resolved_inputs(
                    "Int to String: no int-like value in Start inputs",
                    {"start_keys": list(first.outputs.keys())[:64]},
                )
        else:
            t = _executor_mod()._text_from_stringish_output(first)
            if t is None:
                if hasattr(first, "text"):
                    t = getattr(first, "text")
            if t is None:
                return _executor_mod()._error_with_resolved_inputs(
                    "Int to String: expected int-like upstream output (Int, Start int slot, or parseable string)",
                    {"upstream_type": type(first).__name__},
                )
            parsed = parse_strict_int_for_slot((t or "").strip(), "input")
            if parsed[0] is None:
                return _executor_mod()._error_with_resolved_inputs(
                    f"Int to String: {parsed[1]}",
                    {"text_preview": (t or "")[:2048]},
                )
            n = parsed[0]
        text = str(n)
        details: Dict[str, Any] = {"resolved_inputs": {"value": n, "text": text}}
        if resolved_key is not None:
            details["resolved_inputs"]["start_key"] = resolved_key
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=text),
            "details": details,
        }

    def _resolve_len_from_list_node(
        self, node: LenFromListUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return the length of the upstream list input."""
        data: List[Any] = []
        if upstream:
            first = upstream[0]
            if isinstance(first, ListNodeOutput):
                data = first.data
            elif isinstance(first, StartNodeOutput):
                for val in first.outputs.values():
                    if isinstance(val, list):
                        data = val
                        break
            elif hasattr(first, "data") and isinstance(getattr(first, "data"), list):
                data = getattr(first, "data")
        length = len(data)
        return {
            "status": "ok",
            "output": IntNodeOutput(node_id=node.id, value=length),
            "details": {"resolved_inputs": {"list": data}},
        }

    def _resolve_random_item_from_list_node(
        self, node: RandomItemFromListUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return one uniformly random element from the upstream list (``secrets.randbelow`` index)."""
        data: List[Any] = []
        if upstream:
            first = upstream[0]
            if isinstance(first, ListNodeOutput):
                data = first.data
            elif isinstance(first, StartNodeOutput):
                for val in first.outputs.values():
                    if isinstance(val, list):
                        data = val
                        break
            elif hasattr(first, "data") and isinstance(getattr(first, "data"), list):
                data = getattr(first, "data")
        if len(data) == 0:
            return {"status": "error", "error": "random_item_from_list: list is empty"}
        idx = secrets.randbelow(len(data))
        item = data[idx]
        out: NodeOutputUnion
        if isinstance(item, str):
            out = StringNodeOutput(node_id=node.id, text=item)
        elif isinstance(item, list):
            out = ListNodeOutput(node_id=node.id, data=item)
        elif isinstance(item, dict):
            out = DictionaryNodeOutput(node_id=node.id, data=item)
        elif isinstance(item, int):
            out = IntNodeOutput(node_id=node.id, value=item)
        elif isinstance(item, bool):
            out = BooleanNodeOutput(node_id=node.id, value=item)
        else:
            out = StringNodeOutput(node_id=node.id, text=str(item))
        return {
            "status": "ok",
            "output": out,
            "details": {"resolved_inputs": {"list": data, "picked_index": idx}},
        }

    def _resolve_sandbox_tick_items_node(
        self, node: SandboxTickItemsUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Return ``world.items`` as a JSON-like list from a wired tick dictionary."""
        from app.domain.sandbox.query import filter_items_by_type, item_type_literal, tick_dict_to_items

        data_cfg = node.data or {}
        raw_type_hint = data_cfg.get("item_type")
        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_tick_items: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"item_type": raw_type_hint, "sandbox_tick": None},
            )
        try:
            SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_tick_items: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw, "item_type": raw_type_hint},
            )
        items = tick_dict_to_items(raw)
        data = data_cfg
        raw_type = data.get("item_type")
        if raw_type is None:
            item_type_sel = "all"
        else:
            s = str(raw_type).strip().lower()
            if s in ("", "all"):
                item_type_sel = "all"
            else:
                try:
                    item_type_literal(s)
                except ValueError as exc:
                    return _executor_mod()._error_with_resolved_inputs(
                        f"sandbox_tick_items: {exc}",
                        {"sandbox_tick": raw, "item_type": raw_type},
                    )
                item_type_sel = s
        if item_type_sel != "all":
            items = filter_items_by_type(items, item_type_sel)
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=items),
            "details": {"resolved_inputs": {"item_type": item_type_sel, "item_count": len(items)}},
        }

    def _resolve_sandbox_filter_items_by_type_node(
        self,
        node: SandboxFilterItemsByTypeUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import filter_items_by_type, item_type_literal

        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "items", "type": "list", "value": None},
            {"key": "item_type", "type": "string", "value": "food"},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["items", "item_type"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        items_raw = resolved.get("items")
        if items_raw is None:
            items_raw = []
        if isinstance(items_raw, str):
            try:
                items_raw = json.loads(items_raw)
            except (json.JSONDecodeError, TypeError):
                return _executor_mod()._error_with_resolved_inputs(
                    "sandbox_filter_items_by_type: items must be a list or JSON array",
                    dict(resolved),
                )
        if not isinstance(items_raw, list):
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_filter_items_by_type: items must be a list",
                dict(resolved),
            )
        item_type = resolved.get("item_type")
        if item_type is None or (isinstance(item_type, str) and not item_type.strip()):
            item_type = "food"
        else:
            item_type = str(item_type).strip()
        try:
            item_type_literal(item_type)
        except ValueError as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_filter_items_by_type: {exc}",
                dict(resolved),
            )
        dict_items = [it for it in items_raw if isinstance(it, dict)]
        out = filter_items_by_type(dict_items, item_type)
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=out),
            "details": {"resolved_inputs": {"item_type": item_type, "count": len(out)}},
        }

    def _resolve_sandbox_decision_intent_node(
        self,
        node: SandboxDecisionIntentUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "action", "type": "string", "value": "wander"},
            {"key": "target_item_id", "type": "string", "value": None},
            {"key": "target_cell", "type": "dictionary", "value": None},
            {"key": "reason", "type": "string", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["action", "target_item_id", "target_cell", "reason"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        action = resolved.get("action")
        if action is None or (isinstance(action, str) and not action.strip()):
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_decision_intent: action is required", dict(resolved)
            )
        action_s = str(action).strip()

        tid = resolved.get("target_item_id")
        if tid is not None:
            if isinstance(tid, str) and not tid.strip():
                tid = None
            elif tid is not None:
                tid = str(tid).strip() or None

        tc_raw = resolved.get("target_cell")
        if tc_raw is not None and tc_raw == "":
            tc_raw = None
        if isinstance(tc_raw, str):
            try:
                tc_raw = json.loads(tc_raw)
            except (json.JSONDecodeError, TypeError):
                return _executor_mod()._error_with_resolved_inputs(
                    "sandbox_decision_intent: target_cell must be a JSON object or null",
                    dict(resolved),
                )
        tc: GridCell | None = None
        if tc_raw is not None:
            if not isinstance(tc_raw, dict):
                return _executor_mod()._error_with_resolved_inputs(
                    "sandbox_decision_intent: target_cell must be a dictionary",
                    dict(resolved),
                )
            try:
                tc = GridCell.model_validate(tc_raw)
            except Exception as exc:
                return _executor_mod()._error_with_resolved_inputs(
                    f"sandbox_decision_intent: invalid target_cell: {exc}",
                    dict(resolved),
                )

        reason = resolved.get("reason")
        if reason is not None and reason != "":
            reason = str(reason)
        else:
            reason = None

        try:
            dec = DecisionIntent.model_validate(
                {
                    "action": action_s,
                    "target_item_id": tid,
                    "target_cell": tc.model_dump(mode="json") if tc else None,
                    "reason": reason,
                }
            )
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_decision_intent: {exc}",
                {
                    "action": action_s,
                    "target_item_id": tid,
                    "target_cell": tc.model_dump(mode="json") if tc else None,
                    "reason": reason,
                },
            )
        data = dec.model_dump(mode="json")
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": data},
        }

    def _resolve_sandbox_world_grid_node(
        self, node: SandboxWorldGridUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import world_grid_dimensions_from_tick

        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_world_grid: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_world_grid: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        dims = world_grid_dimensions_from_tick(raw)
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=dims),
            "details": {"resolved_inputs": dims},
        }

    def _resolve_sandbox_available_cells_node(
        self, node: SandboxAvailableCellsUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import available_cells_from_tick_dict

        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_available_cells: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_available_cells: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        cells = available_cells_from_tick_dict(raw)
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=cells),
            "details": {"resolved_inputs": {"cell_count": len(cells)}},
        }

    def _resolve_sandbox_tick_pet_node(
        self, node: SandboxTickPetUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_tick_pet: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            tick_in = SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_tick_pet: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        data = tick_in.pet.model_dump(mode="json")
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"pet": data}},
        }

    def _resolve_sandbox_nearest_item_by_type_node(
        self,
        node: SandboxNearestItemByTypeUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import item_type_literal, nearest_item_dicts_by_type

        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "sandbox_tick", "type": "dictionary", "value": None},
            {"key": "item_type", "type": "string", "value": "food"},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["sandbox_tick", "item_type"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw = resolved.get("sandbox_tick")
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_nearest_item_by_type: connect sandbox_tick",
                dict(resolved),
            )
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return _executor_mod()._error_with_resolved_inputs(
                    "sandbox_nearest_item_by_type: sandbox_tick must be a JSON object or array",
                    dict(resolved),
                )
        if not isinstance(raw, dict):
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_nearest_item_by_type: sandbox_tick must be a dictionary",
                dict(resolved),
            )
        raw_t = resolved.get("item_type")
        if raw_t is None or (isinstance(raw_t, str) and not str(raw_t).strip()):
            item_type_sel = "food"
        else:
            s = str(raw_t).strip().lower()
            if s == "all":
                item_type_sel = "all"
            else:
                try:
                    item_type_literal(s)
                except ValueError as exc:
                    return _executor_mod()._error_with_resolved_inputs(
                        f"sandbox_nearest_item_by_type: {exc}",
                        dict(resolved),
                    )
                item_type_sel = s
        try:
            out = nearest_item_dicts_by_type(raw, item_type_sel)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_nearest_item_by_type: {exc}",
                {**dict(resolved), "item_type": item_type_sel},
            )
        data = out[0] if out else {}
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"item_type": item_type_sel, "has_item": bool(out)}},
        }

    def _resolve_sandbox_closest_item_node(
        self,
        node: SandboxClosestItemUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import item_type_literal, nearest_item_dicts_by_type

        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "sandbox_tick", "type": "dictionary", "value": None},
            {"key": "item_type", "type": "string", "value": "food"},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["sandbox_tick", "item_type"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw = resolved.get("sandbox_tick")
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_closest_item: connect sandbox_tick",
                dict(resolved),
            )
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return _executor_mod()._error_with_resolved_inputs(
                    "sandbox_closest_item: sandbox_tick must be a JSON object or array",
                    dict(resolved),
                )
        if not isinstance(raw, dict):
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_closest_item: sandbox_tick must be a dictionary",
                dict(resolved),
            )
        raw_t = resolved.get("item_type")
        if raw_t is None or (isinstance(raw_t, str) and not str(raw_t).strip()):
            item_type_sel = "food"
        else:
            s = str(raw_t).strip().lower()
            if s == "all":
                item_type_sel = "all"
            else:
                try:
                    item_type_literal(s)
                except ValueError as exc:
                    return _executor_mod()._error_with_resolved_inputs(
                        f"sandbox_closest_item: {exc}",
                        dict(resolved),
                    )
                item_type_sel = s
        try:
            out = nearest_item_dicts_by_type(raw, item_type_sel)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_closest_item: {exc}",
                {**dict(resolved), "item_type": item_type_sel},
            )
        data = out[0] if out else {}
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": {"item_type": item_type_sel, "has_item": bool(out)}},
        }

    def _resolve_sandbox_decision_move_to_node(
        self,
        node: SandboxDecisionMoveToUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "target_item_id", "type": "string", "value": None},
            {"key": "target_cell", "type": "dictionary", "value": None},
            {"key": "reason", "type": "string", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["target_item_id", "target_cell", "reason"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        tid = resolved.get("target_item_id")
        if tid is not None:
            if isinstance(tid, str) and not tid.strip():
                tid = None
            elif tid is not None:
                tid = str(tid).strip() or None

        tc_raw = resolved.get("target_cell")
        if tc_raw is not None and tc_raw == "":
            tc_raw = None
        if isinstance(tc_raw, str):
            try:
                tc_raw = json.loads(tc_raw)
            except (json.JSONDecodeError, TypeError):
                return _executor_mod()._error_with_resolved_inputs(
                    "sandbox_decision_move_to: target_cell must be a JSON object or null",
                    dict(resolved),
                )
        tc: GridCell | None = None
        if tc_raw is not None:
            if not isinstance(tc_raw, dict):
                return _executor_mod()._error_with_resolved_inputs(
                    "sandbox_decision_move_to: target_cell must be a dictionary",
                    dict(resolved),
                )
            try:
                tc = GridCell.model_validate(tc_raw)
            except Exception as exc:
                return _executor_mod()._error_with_resolved_inputs(
                    f"sandbox_decision_move_to: invalid target_cell: {exc}",
                    dict(resolved),
                )

        reason = resolved.get("reason")
        if reason is not None and reason != "":
            reason = str(reason)
        else:
            reason = None

        try:
            dec = DecisionIntent.model_validate(
                {
                    "action": "move_to",
                    "target_item_id": tid,
                    "target_cell": tc.model_dump(mode="json") if tc else None,
                    "reason": reason,
                }
            )
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_decision_move_to: {exc}",
                {
                    "action": "move_to",
                    "target_item_id": tid,
                    "target_cell": tc.model_dump(mode="json") if tc else None,
                    "reason": reason,
                },
            )
        data = dec.model_dump(mode="json")
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=data),
            "details": {"resolved_inputs": data},
        }

    def _resolve_sandbox_starter_decision_node(
        self, node: SandboxStarterDecisionUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Same policy as legacy ``sandbox_behavior`` primitive (starter_behavior_decision)."""
        from app.domain.sandbox.starter_behavior import starter_behavior_decision

        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_starter_decision: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            tick_in = SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_starter_decision: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        try:
            dec = starter_behavior_decision(tick_in)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_starter_decision: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=dec.model_dump(mode="json")),
            "details": {"resolved_inputs": {"sandbox_tick": raw}},
        }

    def _resolve_sandbox_pet_hunger_node(
        self, node: SandboxPetHungerUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import pet_hunger_from_tick_dict

        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_pet_hunger: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            v = pet_hunger_from_tick_dict(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_pet_hunger: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": IntNodeOutput(node_id=node.id, value=int(v)),
            "details": {"resolved_inputs": {"hunger": v}},
        }

    def _resolve_sandbox_pet_energy_node(
        self, node: SandboxPetEnergyUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import pet_energy_from_tick_dict

        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_pet_energy: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            v = pet_energy_from_tick_dict(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_pet_energy: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": IntNodeOutput(node_id=node.id, value=int(v)),
            "details": {"resolved_inputs": {"energy": v}},
        }

    def _resolve_sandbox_pet_cell_node(
        self, node: SandboxPetCellUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import pet_cell_dict_from_tick_dict

        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_pet_cell: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            cell = pet_cell_dict_from_tick_dict(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_pet_cell: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=cell),
            "details": {"resolved_inputs": cell},
        }

    def _resolve_sandbox_is_nearby8_node(
        self,
        node: SandboxIsNearby8UtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import grid_cell_from_jsonable, is_nearby8

        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "cell_a", "type": "dictionary", "value": None},
            {"key": "cell_b", "type": "dictionary", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["cell_a", "cell_b"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )

        def _coerce_cell(label: str, raw: Any) -> GridCell:
            if raw is None:
                raise ValueError(f"{label}: missing value")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except (json.JSONDecodeError, TypeError) as exc:
                    raise ValueError(f"{label}: invalid JSON") from exc
            if isinstance(raw, dict):
                return grid_cell_from_jsonable(raw)
            raise ValueError(f"{label}: expected a dictionary")

        try:
            a = _coerce_cell("cell_a", resolved.get("cell_a"))
            b = _coerce_cell("cell_b", resolved.get("cell_b"))
            ok = is_nearby8(a, b)
        except ValueError as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_is_nearby8: {exc}",
                dict(resolved),
            )
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_is_nearby8: {exc}",
                dict(resolved),
            )
        return {
            "status": "ok",
            "output": BooleanNodeOutput(node_id=node.id, value=ok),
            "details": {
                "resolved_inputs": {
                    "cell_a": a.model_dump(mode="json"),
                    "cell_b": b.model_dump(mode="json"),
                }
            },
        }

    def _resolve_sandbox_first_nearby_food_node(
        self, node: SandboxFirstNearbyFoodUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import first_nearby_food_item_dicts

        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_first_nearby_food: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_first_nearby_food: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        items = first_nearby_food_item_dicts(raw)
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=items),
            "details": {"resolved_inputs": {"count": len(items)}},
        }

    def _resolve_sandbox_first_food_world_order_node(
        self, node: SandboxFirstFoodWorldOrderUtilityNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        from app.domain.sandbox.query import first_food_world_order_item_dicts

        raw = _executor_mod()._sandbox_tick_dict_from_upstream(upstream)
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_first_food_world_order: connect sandbox_tick (Start output) or a tick-shaped dictionary",
                {"sandbox_tick": None},
            )
        try:
            SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_first_food_world_order: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        items = first_food_world_order_item_dicts(raw)
        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=items),
            "details": {"resolved_inputs": {"count": len(items)}},
        }

    def _resolve_list_item_by_index_node(
        self,
        node: ListItemByIndexUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return the item at the given index in the list. Raises ValueError if out of bounds."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "index", "type": "int", "value": 0},
            {"key": "list", "type": "list", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["index", "list"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw_index = resolved.get("index")
        if raw_index is None or raw_index == "":
            return _executor_mod()._error_with_resolved_inputs("Index is required", dict(resolved))
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            return _executor_mod()._error_with_resolved_inputs("Index must be a valid integer", dict(resolved))
        if index < 0:
            return _executor_mod()._error_with_resolved_inputs(
                f"Index {index} is out of bounds: index must be non-negative",
                dict(resolved),
            )
        data = resolved.get("list")
        if data is None:
            data = []
        if not isinstance(data, list):
            try:
                data = json.loads(data) if isinstance(data, str) else list(data)
            except (json.JSONDecodeError, TypeError):
                return _executor_mod()._error_with_resolved_inputs("List input must be a list", dict(resolved))
        if index >= len(data):
            valid_range = f"0-{len(data) - 1}" if data else "empty list has no valid indices"
            return _executor_mod()._error_with_resolved_inputs(
                f"Index {index} is out of bounds: list has {len(data)} items (valid indices: {valid_range})",
                dict(resolved),
            )
        item = data[index]
        out: NodeOutputUnion
        if isinstance(item, str):
            out = StringNodeOutput(node_id=node.id, text=item)
        elif isinstance(item, list):
            out = ListNodeOutput(node_id=node.id, data=item)
        elif isinstance(item, dict):
            out = DictionaryNodeOutput(node_id=node.id, data=item)
        elif isinstance(item, int):
            out = IntNodeOutput(node_id=node.id, value=item)
        elif isinstance(item, bool):
            out = BooleanNodeOutput(node_id=node.id, value=item)
        else:
            out = StringNodeOutput(node_id=node.id, text=str(item))
        return {"status": "ok", "output": out, "details": {"resolved_inputs": {"index": index, "list": data}}}

    def _resolve_dictionary_value_by_key_node(
        self,
        node: DictionaryValueByKeyUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return the value for a key in a dictionary, coerced to a declared primitive output type."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "key", "type": "string", "value": ""},
            {"key": "dictionary", "type": "dictionary", "value": None},
        ]
        raw_ovt = (node.data or {}).get("output_value_type")
        output_value_type = raw_ovt if isinstance(raw_ovt, str) else "list"
        allowed = frozenset({"string", "list", "dictionary", "boolean", "int", "datetime"})
        if output_value_type not in allowed:
            return _executor_mod()._error_with_resolved_inputs(
                f"Dictionary value by key: output_value_type must be one of {sorted(allowed)}; got {output_value_type!r}",
                {"output_value_type": output_value_type},
            )
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["key", "dictionary"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )

        def _snap(extra: dict[str, Any] | None = None) -> dict[str, Any]:
            base: dict[str, Any] = {
                "key": resolved.get("key"),
                "output_value_type": output_value_type,
            }
            rd = resolved.get("dictionary")
            if isinstance(rd, dict):
                base["dictionary_keys"] = list(rd.keys())[:128]
            elif isinstance(rd, str):
                base["dictionary_input_chars"] = len(rd)
            elif rd is not None:
                base["dictionary_type"] = type(rd).__name__
            if extra:
                base.update(extra)
            return base

        raw_key = resolved.get("key")
        if raw_key is None or (isinstance(raw_key, str) and raw_key.strip() == ""):
            return _executor_mod()._error_with_resolved_inputs("Dictionary value by key: key is required", _snap())
        key = str(raw_key).strip() if not isinstance(raw_key, str) else raw_key.strip()

        raw_dict = resolved.get("dictionary")
        d: Dict[str, Any]
        if isinstance(raw_dict, dict):
            d = raw_dict
        elif isinstance(raw_dict, str):
            try:
                parsed = json.loads(raw_dict)
            except (json.JSONDecodeError, TypeError) as e:
                return _executor_mod()._error_with_resolved_inputs(
                    f"Dictionary value by key: invalid JSON for dictionary input ({e})",
                    _snap(),
                )
            if not isinstance(parsed, dict):
                return _executor_mod()._error_with_resolved_inputs(
                    "Dictionary value by key: dictionary input must be a JSON object",
                    _snap(),
                )
            d = parsed
        else:
            return _executor_mod()._error_with_resolved_inputs(
                "Dictionary value by key: dictionary input must be a dictionary",
                _snap(),
            )

        def _matches_expected(v: Any, ovt: str) -> bool:
            if ovt == "string":
                return isinstance(v, str)
            if ovt == "list":
                return isinstance(v, list)
            if ovt == "dictionary":
                return isinstance(v, dict)
            if ovt == "boolean":
                return isinstance(v, bool)
            if ovt == "int":
                return type(v) is int or (isinstance(v, int) and not isinstance(v, bool))
            if ovt == "datetime":
                return isinstance(v, str) and parse_rfc3339_datetime_string(v) is not None
            return False

        def _resolve_optional_fallback() -> tuple[Any, str] | None:
            """
            (value, source) or None.

            Precedence: input override, wire to ``fallback`` (first upstream with output; if an edge
            exists but no output yet, fall through to static), ``data.fallback_value``, then
            ``required_inputs`` entry for key ``fallback`` (non-``None`` value).
            """
            ovr = (input_overrides or {}).get("fallback")
            if ovr is not None:
                return (ovr, "override")
            for edge in edges:
                if edge.target != node.id or edge.target_handle != "fallback":
                    continue
                out = outputs.get(edge.source)
                if out is None:
                    continue
                slot = _get_slot_value(out, edge.source_handle)
                return (node_output_to_input_override_value(slot), "wire")
            if "fallback_value" in (node.data or {}):
                return ((node.data or {})["fallback_value"], "data")
            for item in (node.data or {}).get("required_inputs") or []:
                if not isinstance(item, dict) or item.get("key") != "fallback":
                    continue
                v = item.get("value")
                if v is not None:
                    return (v, "required_input")
            return None

        fb = _resolve_optional_fallback()

        def _build_from_val(
            val: Any,
            *,
            from_fallback: bool,
            value_label: str,
        ) -> Dict[str, Any]:
            if not _matches_expected(val, output_value_type):
                if from_fallback:
                    return _executor_mod()._error_with_resolved_inputs(
                        f"Dictionary value by key: fallback has wrong type for output_value_type={output_value_type!r}",
                        _snap({"value_type": type(val).__name__}),
                    )
                return _executor_mod()._error_with_resolved_inputs(
                    f"Dictionary value by key: value for {value_label!r} has wrong type for output_value_type={output_value_type!r}",
                    _snap({"resolved_key": value_label, "value_type": type(val).__name__}),
                )

            out: NodeOutputUnion
            if output_value_type == "string":
                out = StringNodeOutput(node_id=node.id, text=val)
            elif output_value_type == "list":
                out = ListNodeOutput(node_id=node.id, data=val)
            elif output_value_type == "dictionary":
                out = DictionaryNodeOutput(node_id=node.id, data=val)
            elif output_value_type == "boolean":
                out = BooleanNodeOutput(node_id=node.id, value=val)
            elif output_value_type == "datetime":
                iso = parse_rfc3339_datetime_string(val)
                if iso is None:
                    if from_fallback:
                        return _executor_mod()._error_with_resolved_inputs(
                            f"Dictionary value by key: fallback is not a valid RFC3339 datetime for output_value_type={output_value_type!r}",
                            _snap(),
                        )
                    return _executor_mod()._error_with_resolved_inputs(
                        f"Dictionary value by key: value for {value_label!r} is not a valid RFC3339 datetime",
                        _snap({"resolved_key": value_label}),
                    )
                out = DateTimeNodeOutput(node_id=node.id, iso=iso)
            else:
                out = IntNodeOutput(node_id=node.id, value=int(val))

            ri: dict[str, Any] = {
                "key": key,
                "output_value_type": output_value_type,
                "dictionary_keys": list(d.keys()),
            }
            if from_fallback and fb is not None:
                ri["use_fallback"] = True
                ri["fallback_source"] = fb[1]
            return {
                "status": "ok",
                "output": out,
                "details": {"resolved_inputs": ri},
            }

        _MISSING = object()
        try:
            if key not in d:
                raw_at_key = _MISSING
            else:
                raw_at_key = d[key]
        except KeyError:
            # Rare (``in``/``get`` / dict-like edge cases); treat like missing and use optional fallback
            raw_at_key = _MISSING

        if raw_at_key is not _MISSING and raw_at_key is not None:
            return _build_from_val(
                raw_at_key,
                from_fallback=False,
                value_label=key,
            )

        if fb is not None:
            fval, _fsrc = fb
            return _build_from_val(fval, from_fallback=True, value_label="fallback")

        if raw_at_key is _MISSING:
            return _executor_mod()._error_with_resolved_inputs(
                f"Dictionary value by key: key {key!r} is not present",
                _snap({"resolved_key": key, "dictionary_keys": list(d.keys())[:128]}),
            )
        return _executor_mod()._error_with_resolved_inputs(
            f"Dictionary value by key: value for key {key!r} is null",
            _snap({"resolved_key": key, "dictionary_keys": list(d.keys())[:128]}),
        )

    def _resolve_dictionary_set_value_by_key_node(
        self,
        node: DictionarySetValueByKeyUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Shallow-copy dictionary input and set one top-level key to value (any JSON-serializable)."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "dictionary", "type": "dictionary", "value": None},
            {"key": "key", "type": "string", "value": ""},
            {"key": "value", "type": "any", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["dictionary", "key", "value"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        value_wired = any(e.target == node.id and e.target_handle == "value" for e in edges)
        if input_overrides.get("value") is None:
            for edge in edges:
                if edge.target != node.id or edge.target_handle != "value":
                    continue
                out = outputs.get(edge.source)
                if out is None:
                    continue
                slot = _get_slot_value(out, edge.source_handle)
                resolved["value"] = node_output_to_input_override_value(slot)
                break

        def _snap(extra: dict[str, Any] | None = None) -> dict[str, Any]:
            base: dict[str, Any] = {"key": resolved.get("key")}
            rd = resolved.get("dictionary")
            if isinstance(rd, dict):
                base["dictionary_keys"] = list(rd.keys())[:128]
            elif isinstance(rd, str):
                base["dictionary_input_chars"] = len(rd)
            elif rd is not None:
                base["dictionary_type"] = type(rd).__name__
            if extra:
                base.update(extra)
            return base

        raw_key = resolved.get("key")
        if raw_key is None or (isinstance(raw_key, str) and raw_key.strip() == ""):
            return _executor_mod()._error_with_resolved_inputs("Dictionary set value by key: key is required", _snap())

        key = str(raw_key).strip() if not isinstance(raw_key, str) else raw_key.strip()

        raw_dict = resolved.get("dictionary")
        d: Dict[str, Any]
        if isinstance(raw_dict, dict):
            d = raw_dict
        elif isinstance(raw_dict, str):
            try:
                parsed = json.loads(raw_dict)
            except (json.JSONDecodeError, TypeError) as e:
                return _executor_mod()._error_with_resolved_inputs(
                    f"Dictionary set value by key: invalid JSON for dictionary input ({e})",
                    _snap(),
                )
            if not isinstance(parsed, dict):
                return _executor_mod()._error_with_resolved_inputs(
                    "Dictionary set value by key: dictionary input must be a JSON object",
                    _snap(),
                )
            d = parsed
        else:
            return _executor_mod()._error_with_resolved_inputs(
                "Dictionary set value by key: dictionary input must be a dictionary",
                _snap(),
            )

        raw_val = resolved.get("value")
        if not value_wired and (raw_val is None or raw_val == ""):
            return _executor_mod()._error_with_resolved_inputs(
                "Dictionary set value by key: value is required", _snap()
            )

        item = raw_val
        out_dict = dict(d)
        out_dict[key] = item
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=out_dict),
            "details": {
                "resolved_inputs": {
                    "key": key,
                    "dictionary_keys": list(out_dict.keys()),
                }
            },
        }

    def _resolve_read_document_property_node(
        self,
        node: ReadDocumentPropertyUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Read a named field from a Document primitive output dict (id, name, description, body)."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "target_property", "type": "string", "value": ""},
            {"key": "document", "type": "document", "value": None},
        ]
        raw_ovt = (node.data or {}).get("output_value_type")
        output_value_type = raw_ovt if isinstance(raw_ovt, str) else "string"
        allowed = frozenset({"string", "list", "dictionary", "boolean", "int", "datetime"})
        if output_value_type not in allowed:
            return _executor_mod()._error_with_resolved_inputs(
                f"Read document property: output_value_type must be one of {sorted(allowed)}; got {output_value_type!r}",
                {"output_value_type": output_value_type},
            )
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["target_property", "document"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )

        def _snap(extra: dict[str, Any] | None = None) -> dict[str, Any]:
            base: dict[str, Any] = {
                "target_property": resolved.get("target_property"),
                "output_value_type": output_value_type,
            }
            rd = resolved.get("document")
            if isinstance(rd, dict):
                base["document_keys"] = list(rd.keys())[:128]
            elif isinstance(rd, str):
                base["document_input_chars"] = len(rd)
            elif rd is not None:
                base["document_type"] = type(rd).__name__
            if extra:
                base.update(extra)
            return base

        raw_key = resolved.get("target_property")
        if raw_key is None or (isinstance(raw_key, str) and raw_key.strip() == ""):
            return _executor_mod()._error_with_resolved_inputs(
                "Read document property: target_property is required", _snap()
            )
        prop_key = str(raw_key).strip() if not isinstance(raw_key, str) else raw_key.strip()

        raw_doc = resolved.get("document")
        d: Dict[str, Any]
        if isinstance(raw_doc, dict):
            d = raw_doc
        elif isinstance(raw_doc, str):
            try:
                parsed = json.loads(raw_doc)
            except (json.JSONDecodeError, TypeError) as e:
                return _executor_mod()._error_with_resolved_inputs(
                    f"Read document property: invalid JSON for document input ({e})",
                    _snap(),
                )
            if not isinstance(parsed, dict):
                return _executor_mod()._error_with_resolved_inputs(
                    "Read document property: document input must be a dictionary",
                    _snap(),
                )
            d = parsed
        else:
            return _executor_mod()._error_with_resolved_inputs(
                "Read document property: document input must be a dictionary",
                _snap(),
            )

        if prop_key not in d:
            return _executor_mod()._error_with_resolved_inputs(
                f"Read document property: property {prop_key!r} is not present",
                _snap({"resolved_property": prop_key, "document_keys": list(d.keys())[:128]}),
            )
        val = d[prop_key]
        if val is None:
            return _executor_mod()._error_with_resolved_inputs(
                f"Read document property: value for property {prop_key!r} is null",
                _snap({"resolved_property": prop_key, "document_keys": list(d.keys())[:128]}),
            )

        def _matches_expected(v: Any, ovt: str) -> bool:
            if ovt == "string":
                return isinstance(v, str)
            if ovt == "list":
                return isinstance(v, list)
            if ovt == "dictionary":
                return isinstance(v, dict)
            if ovt == "boolean":
                return isinstance(v, bool)
            if ovt == "int":
                return type(v) is int or (isinstance(v, int) and not isinstance(v, bool))
            if ovt == "datetime":
                return isinstance(v, str) and parse_rfc3339_datetime_string(v) is not None
            return False

        if not _matches_expected(val, output_value_type):
            return _executor_mod()._error_with_resolved_inputs(
                f"Read document property: value for {prop_key!r} has wrong type for output_value_type={output_value_type!r}",
                _snap({"resolved_property": prop_key, "value_type": type(val).__name__}),
            )

        out: NodeOutputUnion
        if output_value_type == "string":
            out = StringNodeOutput(node_id=node.id, text=val)
        elif output_value_type == "list":
            out = ListNodeOutput(node_id=node.id, data=val)
        elif output_value_type == "dictionary":
            out = DictionaryNodeOutput(node_id=node.id, data=val)
        elif output_value_type == "boolean":
            out = BooleanNodeOutput(node_id=node.id, value=val)
        elif output_value_type == "datetime":
            iso = parse_rfc3339_datetime_string(val)
            if iso is None:
                return _executor_mod()._error_with_resolved_inputs(
                    f"Read document property: value for {prop_key!r} is not a valid RFC3339 datetime",
                    _snap({"resolved_property": prop_key}),
                )
            out = DateTimeNodeOutput(node_id=node.id, iso=iso)
        else:
            out = IntNodeOutput(node_id=node.id, value=int(val))

        return {
            "status": "ok",
            "output": out,
            "details": {
                "resolved_inputs": {
                    "target_property": prop_key,
                    "output_value_type": output_value_type,
                    "document_keys": list(d.keys()),
                }
            },
        }

    def _resolve_add_to_list_node(
        self,
        node: AddToListUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        *,
        loop_list_carry: Optional[Dict[tuple[str, str], list[Any]]],
        for_loop_id: Optional[str],
    ) -> Dict[str, Any]:
        """Append a value to a list (any JSON-serializable item). In a For loop body, list state carries across iterations."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "list", "type": "list", "value": None},
            {"key": "value", "type": "any", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["list", "value"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        value_wired = any(e.target == node.id and e.target_handle == "value" for e in edges)
        if input_overrides.get("value") is None:
            for edge in edges:
                if edge.target != node.id or edge.target_handle != "value":
                    continue
                out = outputs.get(edge.source)
                if out is None:
                    continue
                slot = _get_slot_value(out, edge.source_handle)
                resolved["value"] = node_output_to_input_override_value(slot)
                break

        carry_bundle = loop_list_carry
        fk = for_loop_id
        carry_key: tuple[str, str] | None = (fk, node.id) if fk and carry_bundle is not None else None
        base_list: list[Any]
        if carry_bundle is not None and carry_key is not None and carry_key in carry_bundle:
            base_list = list(carry_bundle[carry_key])
        else:
            raw_list = resolved.get("list")
            if raw_list is None or (isinstance(raw_list, str) and str(raw_list).strip() == ""):
                return {"status": "error", "error": "Add to list: list input is required"}
            if not isinstance(raw_list, list):
                return {"status": "error", "error": "Add to list: list input must be a list"}
            base_list = list(raw_list)

        raw_val = resolved.get("value")
        if not value_wired and (raw_val is None or raw_val == ""):
            return {"status": "error", "error": "Add to list: value is required"}

        item = raw_val
        new_list = base_list + [item]
        if carry_key is not None and carry_bundle is not None:
            carry_bundle[carry_key] = new_list

        return {
            "status": "ok",
            "output": ListNodeOutput(node_id=node.id, data=new_list),
            "details": {
                "resolved_inputs": {
                    "list": base_list,
                    "value": item,
                    "result_length": len(new_list),
                }
            },
        }

    def _resolve_string_trunc_node(
        self,
        node: StringTruncUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return substring with inclusive ``end_index`` (0-based), or ``end_index == -1`` through end."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "target_string", "type": "string", "value": None},
            {"key": "start_index", "type": "int", "value": 0},
            {"key": "end_index", "type": "int", "value": -1},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["target_string", "start_index", "end_index"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw_target = resolved.get("target_string")
        text = raw_target if isinstance(raw_target, str) else ("" if raw_target is None else str(raw_target))

        def _err(msg: str) -> dict[str, Any]:
            return _executor_mod()._error_with_resolved_inputs(
                msg, _executor_mod()._string_trunc_error_resolved(resolved)
            )

        raw_start = resolved.get("start_index")
        if raw_start is None or raw_start == "":
            return _err("String trunc: start_index is required")
        try:
            start_i = int(raw_start)
        except (TypeError, ValueError):
            return _err("String trunc: start_index must be a valid integer")
        if start_i < 0:
            return _err(f"String trunc: start_index must be non-negative (got {start_i})")

        raw_end = resolved.get("end_index")
        if raw_end is None or raw_end == "":
            return _err("String trunc: end_index is required")
        try:
            end_i = int(raw_end)
        except (TypeError, ValueError):
            return _err("String trunc: end_index must be a valid integer")
        if end_i < -1:
            return _err(f"String trunc: end_index must be -1 or non-negative (got {end_i})")
        if end_i >= 0 and end_i < start_i:
            return _err(f"String trunc: end_index ({end_i}) must be >= start_index ({start_i}) unless end_index is -1")

        result = text[start_i:] if end_i == -1 else text[start_i : end_i + 1]
        detail = _executor_mod()._string_trunc_resolved_inputs_payload(text, start_i, end_i, result=result)
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=result),
            "details": {"resolved_inputs": detail},
        }

    def _resolve_prepend_text_node(
        self,
        node: PrependTextUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Prepend text to target string, with optional blank line between."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["target_string", "text_to_prepend"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        target_string = resolved.get("target_string") or ""
        text_to_prepend = resolved.get("text_to_prepend") or ""
        add_additional_line = node.data.get("add_additional_line") is True
        sep = "\n\n" if add_additional_line else ""
        output = (text_to_prepend or "") + sep + (target_string or "")
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=output),
            "details": {
                "resolved_inputs": {
                    "target_string": target_string,
                    "text_to_prepend": text_to_prepend,
                    "add_additional_line": add_additional_line,
                }
            },
        }

    def _resolve_message_utility_node(
        self,
        node: MessageUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Surface wired text to the client as ``details.user_message``; no data output (empty string)."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["message"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw = resolved.get("message")
        text = _executor_mod()._coerce_message_display_text(raw)
        if len(text) > _executor_mod().MESSAGE_UTILITY_MAX_LEN:
            text = text[: _executor_mod().MESSAGE_UTILITY_MAX_LEN]
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=""),
            "details": {
                "resolved_inputs": {"message": raw},
                "user_message": text,
            },
        }

    def _resolve_basic_conditional_node(
        self,
        node: BasicConditionalControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate condition and return ConditionalNodeOutput with branch 'true' or 'false'."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["condition"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        condition_val = resolved.get("condition")
        if condition_val is None or (isinstance(condition_val, str) and condition_val.strip() == ""):
            condition_val = node.data.get("condition")
        branch = "true" if _condition_to_bool(condition_val) else "false"
        return {
            "status": "ok",
            "output": ConditionalNodeOutput(node_id=node.id, branch=branch),
            "details": {"resolved_inputs": {"condition": condition_val}},
        }

    def _resolve_is_node(
        self,
        node: IsControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compare input_a and input_b for equality; return ConditionalNodeOutput with branch 'true' or 'false'."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["input_a", "input_b"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        input_a = resolved.get("input_a")
        input_b = resolved.get("input_b")
        branch = "true" if _values_equal(input_a, input_b) else "false"
        return {
            "status": "ok",
            "output": ConditionalNodeOutput(node_id=node.id, branch=branch),
            "details": {"resolved_inputs": {"input_a": input_a, "input_b": input_b}},
        }

    def _resolve_is_empty_node(
        self,
        node: IsEmptyControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """True branch when ``value`` is ``[]`` or ``{}``; false when non-empty list or dict."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "value", "type": "any", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["value"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        val = resolved.get("value")
        if val is None:
            return _executor_mod()._error_with_resolved_inputs(
                "is_empty: connect value (list or dictionary)",
                dict(resolved),
            )
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return _executor_mod()._error_with_resolved_inputs(
                    "is_empty: value must be a list or dictionary",
                    dict(resolved),
                )
        if not isinstance(val, (list, dict)):
            return _executor_mod()._error_with_resolved_inputs(
                "is_empty: value must be a list or dictionary",
                dict(resolved),
            )
        is_empty = len(val) == 0
        branch = "true" if is_empty else "false"
        return {
            "status": "ok",
            "output": ConditionalNodeOutput(node_id=node.id, branch=branch),
            "details": {"resolved_inputs": {"value": val}},
        }

    def _resolve_comparison_node(
        self,
        node: Any,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        op: str,
    ) -> Dict[str, Any]:
        """Shared logic for Gt, Lt, Gte, Lte. op is 'gt', 'lt', 'gte', or 'lte'."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id, ["input_a", "input_b"], edges, outputs, input_overrides, raw_inputs
        )
        input_a, input_b = resolved.get("input_a"), resolved.get("input_b")
        a_val, b_val = _to_comparable(input_a, input_b)
        if op == "gt":
            result = a_val > b_val
        elif op == "lt":
            result = a_val < b_val
        elif op == "gte":
            result = a_val >= b_val
        else:
            result = a_val <= b_val
        branch = "true" if result else "false"
        return {
            "status": "ok",
            "output": ConditionalNodeOutput(node_id=node.id, branch=branch),
            "details": {"resolved_inputs": {"input_a": input_a, "input_b": input_b}},
        }

    def _resolve_gt_node(
        self,
        node: GtControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_comparison_node(node, edges, outputs, overrides, "gt")

    def _resolve_lt_node(
        self,
        node: LtControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_comparison_node(node, edges, outputs, overrides, "lt")

    def _resolve_gte_node(
        self,
        node: GteControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_comparison_node(node, edges, outputs, overrides, "gte")

    def _resolve_lte_node(
        self,
        node: LteControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_comparison_node(node, edges, outputs, overrides, "lte")

    def _resolve_logical_node(
        self,
        node: Any,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        op: str,
    ) -> Dict[str, Any]:
        """Shared logic for And, Or, Xor. op is 'and', 'or', or 'xor'."""
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(
            node.id, ["input_a", "input_b"], edges, outputs, input_overrides, raw_inputs
        )
        a_bool = _condition_to_bool(resolved.get("input_a"))
        b_bool = _condition_to_bool(resolved.get("input_b"))
        if op == "and":
            result = a_bool and b_bool
        elif op == "or":
            result = a_bool or b_bool
        else:
            result = a_bool != b_bool
        return {
            "status": "ok",
            "output": BooleanNodeOutput(node_id=node.id, value=result),
            "details": {"resolved_inputs": {"input_a": resolved.get("input_a"), "input_b": resolved.get("input_b")}},
        }

    def _resolve_and_node(
        self,
        node: AndControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_logical_node(node, edges, outputs, overrides, "and")

    def _resolve_or_node(
        self,
        node: OrControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_logical_node(node, edges, outputs, overrides, "or")

    def _resolve_xor_node(
        self,
        node: XorControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        return self._resolve_logical_node(node, edges, outputs, overrides, "xor")

    def _resolve_binary_int_math_node(
        self,
        node: Any,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        op: str,
    ) -> Dict[str, Any]:
        """add | sub | mul | div | mod | min | max — two int inputs input_a, input_b → IntNodeOutput."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "input_a", "type": "int", "value": 0},
            {"key": "input_b", "type": "int", "value": 0},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["input_a", "input_b"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        a_raw, b_raw = resolved.get("input_a"), resolved.get("input_b")
        a_t = parse_strict_int_for_slot(a_raw, "input_a")
        if a_t[1] is not None:
            return {"status": "error", "error": a_t[1]}
        b_t = parse_strict_int_for_slot(b_raw, "input_b")
        if b_t[1] is not None:
            return {"status": "error", "error": b_t[1]}
        a, b = a_t[0], b_t[0]
        assert a is not None and b is not None

        if op in ("div", "mod") and b == 0:
            return {"status": "error", "error": "input_b is zero (division by zero)"}

        if op == "add":
            out = a + b
        elif op == "sub":
            out = a - b
        elif op == "mul":
            out = a * b
        elif op == "div":
            out = int(a / b)
        elif op == "mod":
            out = a % b
        elif op == "min":
            out = min(a, b)
        else:
            out = max(a, b)

        return {
            "status": "ok",
            "output": IntNodeOutput(node_id=node.id, value=out),
            "details": {"resolved_inputs": {"input_a": a, "input_b": b, "op": op}},
        }

    def _resolve_add_days_node(
        self,
        node: AddDaysUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """RFC3339 instant + signed whole days → DateTimeNodeOutput (UTC timedelta days)."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "input", "type": "datetime", "value": None},
            {"key": "days", "type": "int", "value": 0},
        ]
        resolved_map = _resolve_inputs_by_target_handle(
            node.id,
            ["input", "days"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        dt_raw = resolved_map.get("input")
        days_raw = resolved_map.get("days")
        norm = parse_rfc3339_datetime_string(dt_raw)
        if norm is None:
            return _executor_mod()._error_with_resolved_inputs(
                "Add days: input is not a valid RFC3339 datetime (wire a DateTime or set a static instant).",
                {"input": dt_raw, "days": days_raw},
            )
        days_t = parse_strict_int_for_slot(days_raw, "days")
        if days_t[1] is not None:
            return _executor_mod()._error_with_resolved_inputs(
                f"Add days: {days_t[1]}",
                {"input": norm, "days": days_raw},
            )
        dcount = days_t[0]
        assert dcount is not None
        out_iso = shift_rfc3339_instant_by_days(norm, dcount)
        if out_iso is None:
            return _executor_mod()._error_with_resolved_inputs(
                "Add days: could not shift datetime.",
                {"input": norm, "days": dcount},
            )
        return {
            "status": "ok",
            "output": DateTimeNodeOutput(node_id=node.id, iso=out_iso),
            "details": {"resolved_inputs": {"input": norm, "days": dcount}},
        }

    def _resolve_not_node(
        self,
        node: NotControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = node.data.get("required_inputs") or []
        resolved = _resolve_inputs_by_target_handle(node.id, ["input"], edges, outputs, input_overrides, raw_inputs)
        input_val = resolved.get("input")
        result = not _condition_to_bool(input_val)
        return {
            "status": "ok",
            "output": BooleanNodeOutput(node_id=node.id, value=result),
            "details": {"resolved_inputs": {"input": input_val}},
        }

    def _resolve_between_node(
        self,
        node: BetweenControlNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "low", "type": "int", "value": 0},
            {"key": "value", "type": "int", "value": 0},
            {"key": "high", "type": "int", "value": 0},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["low", "value", "high"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        low_t = parse_strict_int_for_slot(resolved.get("low"), "low")
        if low_t[1] is not None:
            return {"status": "error", "error": low_t[1]}
        val_t = parse_strict_int_for_slot(resolved.get("value"), "value")
        if val_t[1] is not None:
            return {"status": "error", "error": val_t[1]}
        high_t = parse_strict_int_for_slot(resolved.get("high"), "high")
        if high_t[1] is not None:
            return {"status": "error", "error": high_t[1]}
        low, value, high = low_t[0], val_t[0], high_t[0]
        assert low is not None and value is not None and high is not None
        if low > high:
            return {
                "status": "error",
                "error": f"low ({low}) must be <= high ({high})",
            }
        branch = "true" if low <= value <= high else "false"
        return {
            "status": "ok",
            "output": ConditionalNodeOutput(node_id=node.id, branch=branch),
            "details": {"resolved_inputs": {"low": low, "value": value, "high": high}},
        }

    def _resolve_structure_primitive_node(self, node: StructurePrimitiveNode) -> Dict[str, Any]:
        """Load Structure by structure_id and return StructureNodeOutput with parsed schema."""
        structure_id_raw = (node.data or {}).get("structure_id")
        if not structure_id_raw:
            return {
                "status": "error",
                "error": f"Structure primitive node '{node.id}' requires structure_id. Select a Structure in the Workflow Editor.",
                "details": {"resolved_inputs": {"structure_id": None}},
            }
        try:
            sid = UUID(structure_id_raw) if isinstance(structure_id_raw, str) else structure_id_raw
        except (ValueError, TypeError):
            return {
                "status": "error",
                "error": f"Structure primitive node '{node.id}' has invalid structure_id.",
                "details": {"resolved_inputs": {"structure_id": structure_id_raw}},
            }
        structure = self.session.exec(
            select(Structure).where(
                col(Structure.id) == sid,
                or_(col(Structure.user_id) == self.user_id, col(Structure.user_id).is_(None)),
            )
        ).first()
        if not structure:
            return {
                "status": "error",
                "error": f"Structure '{structure_id_raw}' not found.",
                "details": {"resolved_inputs": {"structure_id": str(sid)}},
            }
        try:
            schema = json.loads(structure.json_schema)
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"Structure '{structure.name}' has invalid json_schema: {e}",
                "details": {
                    "resolved_inputs": {"structure_id": str(sid), "structure_name": structure.name},
                },
            }
        return {
            "status": "ok",
            "output": StructureNodeOutput(node_id=node.id, schema_dict=schema),
            "details": {
                "resolved_inputs": {
                    "structure_id": str(sid),
                    "structure_name": structure.name,
                }
            },
        }

    def _resolve_sandbox_behavior_primitive_node(
        self, node: SandboxBehaviorPrimitiveNode, upstream: list[NodeOutputUnion]
    ) -> Dict[str, Any]:
        """Map ``SandboxTickInput`` (from Start) to a ``DecisionIntent`` dictionary."""
        from app.domain.sandbox.starter_behavior import starter_behavior_decision
        from app.domain.schemas.sandbox import SandboxTickInput

        raw: dict | None = None
        for out in upstream:
            if isinstance(out, DictionaryNodeOutput):
                raw = dict(out.data)
                break
            if isinstance(out, StartNodeOutput):
                st = out.outputs.get("sandbox_tick")
                if isinstance(st, dict):
                    raw = st
                    break
        if raw is None:
            return _executor_mod()._error_with_resolved_inputs(
                "sandbox_behavior: missing sandbox_tick input",
                {"sandbox_tick": None},
            )
        try:
            tick_in = SandboxTickInput.model_validate(raw)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_behavior: invalid SandboxTickInput: {exc}",
                {"sandbox_tick": raw},
            )
        try:
            dec = starter_behavior_decision(tick_in)
        except Exception as exc:
            return _executor_mod()._error_with_resolved_inputs(
                f"sandbox_behavior: {exc}",
                {"sandbox_tick": raw},
            )
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=dec.model_dump(mode="json")),
            "details": {"resolved_inputs": {"sandbox_tick": raw}},
        }

    def _resolve_document_primitive_node(self, node: DocumentPrimitiveNode) -> Dict[str, Any]:
        """Load Document by document_id and return DocumentNodeOutput."""
        document_id_raw = (node.data or {}).get("document_id")
        if not document_id_raw:
            return {
                "status": "error",
                "error": f"Document primitive node '{node.id}' requires document_id. Select a Document in the Workflow Editor.",
                "details": {"resolved_inputs": {"document_id": None}},
            }
        try:
            did = UUID(document_id_raw) if isinstance(document_id_raw, str) else document_id_raw
        except (ValueError, TypeError):
            return {
                "status": "error",
                "error": f"Document primitive node '{node.id}' has invalid document_id.",
                "details": {"resolved_inputs": {"document_id": document_id_raw}},
            }
        doc = self.session.exec(
            select(Document).where(
                col(Document.id) == did,
                or_(col(Document.user_id) == self.user_id, col(Document.user_id).is_(None)),
            )
        ).first()
        if not doc:
            return {
                "status": "error",
                "error": f"Document '{document_id_raw}' not found.",
                "details": {"resolved_inputs": {"document_id": str(did)}},
            }
        return {
            "status": "ok",
            "output": DocumentNodeOutput(
                node_id=node.id,
                document_id=str(doc.id),
                name=doc.name,
                description=doc.description or "",
                markdown=doc.body or "",
            ),
            "details": {
                "resolved_inputs": {
                    "document_id": str(doc.id),
                    "document_name": doc.name,
                }
            },
        }

    def _artifact_uuid_from_image_payload(self, d: dict[str, Any]) -> Optional[UUID]:
        """Resolve artifact id from a flat ref or a ``capture_url_snapshot``-style ``data`` dict."""
        inner = d.get("image")
        if isinstance(inner, dict):
            raw: Any = inner.get("artifact_id") or inner.get("id")
        else:
            raw = d.get("artifact_id") or d.get("id")
        if raw is None:
            return None
        try:
            return UUID(str(raw).strip())
        except (ValueError, TypeError):
            return None

    def _resolve_image_primitive_node(
        self,
        node: ImagePrimitiveNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """User artifact ref and/or wired image dict → normalized ``DictionaryNodeOutput`` (metadata only)."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "image", "type": "dictionary", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(node.id, ["image"], edges, outputs, input_overrides, raw_inputs)
        wired = resolved.get("image")
        aid: Optional[UUID] = None
        if wired is not None and wired != "":
            if not isinstance(wired, dict):
                return _executor_mod()._error_with_resolved_inputs(
                    "image primitive: wired `image` must be a dictionary (artifact ref or URL snapshot output).",
                    {"image": wired},
                )
            aid = self._artifact_uuid_from_image_payload(wired)
            if aid is None:
                return _executor_mod()._error_with_resolved_inputs(
                    "image primitive: could not read artifact_id from wired image input.",
                    {"image": wired},
                )
        if aid is None:
            raw_aid = (node.data or {}).get("artifact_id")
            if raw_aid:
                try:
                    aid = UUID(str(raw_aid).strip())
                except (ValueError, TypeError):
                    return _executor_mod()._error_with_resolved_inputs(
                        f"image primitive: invalid artifact_id in node data {raw_aid!r}",
                        {"artifact_id": raw_aid},
                    )
        if aid is None:
            return _executor_mod()._error_with_resolved_inputs(
                "image primitive: no image — wire an upstream image output or select a file (artifact_id on the node).",
                {"artifact_id": None, "image": wired},
            )
        row = self.session.exec(
            select(UrlSnapshotArtifact).where(
                col(UrlSnapshotArtifact.id) == aid,
                col(UrlSnapshotArtifact.user_id) == self.user_id,
            )
        ).first()
        if row is None:
            return _executor_mod()._error_with_resolved_inputs(
                f"image primitive: image artifact {aid} not found or not owned by this user.",
                {"artifact_id": str(aid)},
            )
        payload: Dict[str, Any] = {
            "artifact_id": str(row.id),
            "mime_type": (row.mime_type or "image/png").strip() or "image/png",
            "width": int(row.width),
            "height": int(row.height),
        }
        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=payload),
            "details": {"resolved_inputs": {"image": payload}},
        }

    def _resolve_gmail_primitive_node(
        self,
        node: GmailPrimitiveNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Static ``message`` in node data and/or wired ``gmail`` input → ``GmailNodeOutput``."""
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "gmail", "type": "gmail", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["gmail"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        wired = resolved.get("gmail")
        static_raw = (node.data or {}).get("message")

        def _to_plain(val: Any) -> Optional[Dict[str, Any]]:
            if val is None:
                return None
            if isinstance(val, dict):
                return dict(val)
            if isinstance(val, str) and val.strip():
                try:
                    p = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return None
                return p if isinstance(p, dict) else None
            return None

        d: Optional[Dict[str, Any]] = None
        if wired is not None:
            d = _to_plain(wired)
        if d is None and static_raw is not None:
            d = _to_plain(static_raw)

        if not d:
            return _executor_mod()._error_with_resolved_inputs(
                "Gmail primitive requires a non-empty message in node data or a wired gmail input.",
                {"gmail": wired, "has_static_message": static_raw is not None},
            )

        out = gmail_dict_to_node_output(node.id, d)
        return {
            "status": "ok",
            "output": out,
            "details": {
                "resolved_inputs": {
                    "gmail_source": "wire" if wired is not None else "data",
                }
            },
        }

    @staticmethod
    def _document_plain_dict(raw_doc: Any) -> Dict[str, Any]:
        if isinstance(raw_doc, dict):
            return raw_doc
        if isinstance(raw_doc, str):
            try:
                parsed = json.loads(raw_doc)
            except (json.JSONDecodeError, TypeError) as e:
                raise ValueError(f"document input: invalid JSON ({e})") from e
            if not isinstance(parsed, dict):
                raise ValueError("document input must be a dictionary")
            return parsed
        raise ValueError("document input must be a dictionary")

    @staticmethod
    def _document_body_text(d: Dict[str, Any]) -> str:
        if "body" in d:
            return str(d["body"])
        if "markdown" in d:
            return str(d["markdown"])
        raise ValueError("document input has no body or markdown field")

    def _resolve_load_document_node(
        self,
        node: LoadDocumentUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "document_id", "type": "string", "value": None},
            {"key": "document_name", "type": "string", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["document_id", "document_name"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        did_raw = resolved.get("document_id")
        dname_raw = resolved.get("document_name")

        def _nonempty(v: Any) -> bool:
            if v is None:
                return False
            if isinstance(v, str) and not v.strip():
                return False
            return True

        id_ok = _nonempty(did_raw)
        name_ok = _nonempty(dname_raw)
        if id_ok and name_ok:
            return {
                "status": "error",
                "error": "Load document: provide exactly one of document_id or document_name, not both.",
                "details": {"resolved_inputs": {"lookup_mode": "invalid"}},
            }
        if not id_ok and not name_ok:
            return {
                "status": "error",
                "error": "Load document: document_id or document_name is required.",
                "details": {"resolved_inputs": {"document_id": None, "document_name": None}},
            }

        svc = DocumentService(self.session, self.user_id)
        doc: Optional[Document] = None
        ri: Dict[str, Any] = {"lookup_mode": "id" if id_ok else "name"}
        if id_ok:
            try:
                did = UUID(str(did_raw).strip()) if not isinstance(did_raw, UUID) else did_raw
            except (ValueError, TypeError):
                return {
                    "status": "error",
                    "error": "Load document: invalid document_id.",
                    "details": {"resolved_inputs": {"document_id": str(did_raw), "lookup_mode": "id"}},
                }
            doc = svc.get_document(did)
            ri["document_id"] = str(did)
        else:
            name = str(dname_raw).strip()
            doc = svc.get_document_by_name(name)
            ri["document_name"] = name

        if not doc:
            return {
                "status": "error",
                "error": "Load document: document not found.",
                "details": {"resolved_inputs": ri},
            }
        return {
            "status": "ok",
            "output": DocumentNodeOutput(
                node_id=node.id,
                document_id=str(doc.id),
                name=doc.name,
                description=doc.description or "",
                markdown=doc.body or "",
            ),
            "details": {
                "resolved_inputs": {
                    **ri,
                    "resolved_document_id": str(doc.id),
                    "resolved_document_name": doc.name,
                }
            },
        }

    def _resolve_upsert_document_node(
        self,
        node: UpsertDocumentUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "name", "type": "string", "value": ""},
            {"key": "content", "type": "string", "value": ""},
            {"key": "existing_document_id", "type": "string", "value": None},
            {"key": "write_mode", "type": "string", "value": "replace"},
        ]
        upsert_edges = _executor_mod()._normalize_edges_for_upsert_document(node.id, edges)
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["name", "content", "existing_document_id", "write_mode"],
            upsert_edges,
            outputs,
            input_overrides,
            raw_inputs,
            implicit_null_target_wire_string_keys=frozenset({"name", "content"}),
        )
        resolved = _executor_mod()._recover_upsert_miswired_body_into_content(
            node.id, upsert_edges, resolved, raw_inputs
        )
        name = resolved.get("name")
        content = resolved.get("content")
        if name is None or (isinstance(name, str) and not str(name).strip()):
            return {
                "status": "error",
                "error": "Upsert document: name is required.",
                "details": {"resolved_inputs": {"write_mode": resolved.get("write_mode")}},
            }
        if content is None:
            return {
                "status": "error",
                "error": "Upsert document: content is required.",
                "details": {"resolved_inputs": {"document_name": str(name).strip()}},
            }
        content_str = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        wm_raw = resolved.get("write_mode") or "replace"
        wm = str(wm_raw).strip().lower()
        if wm not in ("replace", "append", "merge_json"):
            return {
                "status": "error",
                "error": f"Upsert document: invalid write_mode {wm_raw!r}.",
                "details": {"resolved_inputs": {"document_name": str(name).strip(), "write_mode": wm_raw}},
            }

        ex_raw = resolved.get("existing_document_id")
        ex_id: Optional[UUID] = None
        if ex_raw is not None and str(ex_raw).strip() != "":
            try:
                ex_id = UUID(str(ex_raw).strip()) if not isinstance(ex_raw, UUID) else ex_raw
            except (ValueError, TypeError):
                return {
                    "status": "error",
                    "error": "Upsert document: invalid existing_document_id.",
                    "details": {"resolved_inputs": {"document_name": str(name).strip()}},
                }

        svc = DocumentService(self.session, self.user_id)
        try:
            doc = svc.upsert_document(
                name=str(name).strip(),
                content=content_str,
                existing_document_id=ex_id,
                write_mode=cast(Literal["replace", "append", "merge_json"], wm),
            )
        except ValueError as e:
            return {
                "status": "error",
                "error": str(e),
                "details": {
                    "resolved_inputs": {
                        "document_name": str(name).strip(),
                        "write_mode": wm,
                        "content_chars": len(content_str),
                    }
                },
            }

        return {
            "status": "ok",
            "output": DocumentNodeOutput(
                node_id=node.id,
                document_id=str(doc.id),
                name=doc.name,
                description=doc.description or "",
                markdown=doc.body or "",
            ),
            "details": {
                "resolved_inputs": {
                    "document_name": doc.name,
                    "write_mode": wm,
                    "resolved_document_id": str(doc.id),
                    "content_chars": len(content_str),
                }
            },
        }

    def _resolve_parse_document_body_node(
        self,
        node: ParseDocumentBodyUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "document", "type": "document", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["document"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        try:
            d = self._document_plain_dict(resolved.get("document"))
            text = self._document_body_text(d)
        except ValueError as e:
            return _executor_mod()._error_with_resolved_inputs(str(e), dict(resolved))
        try:
            parsed = json.loads(text.strip())
        except json.JSONDecodeError as e:
            return {
                "status": "error",
                "error": f"Parse document body: invalid JSON ({e})",
                "details": {"resolved_inputs": {"text_chars": len(text)}},
            }
        if isinstance(parsed, dict):
            return {
                "status": "ok",
                "output": DictionaryNodeOutput(node_id=node.id, data=parsed),
                "details": {"resolved_inputs": {"json_kind": "object"}},
            }
        if isinstance(parsed, list):
            return {
                "status": "ok",
                "output": ListNodeOutput(node_id=node.id, data=parsed),
                "details": {"resolved_inputs": {"json_kind": "array"}},
            }
        return {
            "status": "error",
            "error": "Parse document body: JSON root must be an object or array.",
            "details": {"resolved_inputs": {"json_kind": type(parsed).__name__}},
        }

    def _resolve_html_parse_basic_node(
        self,
        node: HtmlParseBasicUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "html", "type": "string", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["html"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        raw = resolved.get("html")
        if raw is None:
            html_s = ""
        elif isinstance(raw, str):
            html_s = raw
        else:
            html_s = str(raw)

        n = len(html_s)
        nd = node.data or {}
        raw_g = nd.get("granularity")
        raw_cr = nd.get("content_root_css")
        granularity: str | None = raw_g if isinstance(raw_g, str) else (str(raw_g) if raw_g is not None else None)
        content_root_css: str | None
        if isinstance(raw_cr, str):
            content_root_css = raw_cr
        elif raw_cr is None:
            content_root_css = None
        else:
            content_root_css = str(raw_cr)

        if not (html_s or "").strip():
            out_data: Dict[str, Any] = {"title": "", "text_blocks": [], "links": []}
        else:
            try:
                out_data = parse_html_basic(
                    html_s,
                    granularity=granularity,
                    content_root_css=content_root_css,
                )
            except ValueError as exc:
                return {
                    "status": "error",
                    "error": str(exc),
                    "details": {
                        "resolved_inputs": {
                            "input_chars": n,
                            "granularity": granularity,
                            "content_root_css": content_root_css,
                        }
                    },
                }

        if n <= _executor_mod().STRING_TRUNC_RESOLVED_TARGET_MAX_CHARS:
            ri: Dict[str, Any] = {
                "input_chars": n,
                "text_blocks_count": len(out_data.get("text_blocks") or []),
                "links_count": len(out_data.get("links") or []),
                "granularity": granularity,
                "content_root_css": content_root_css,
            }
        else:
            ri = {
                "input_chars": n,
                "input_truncated": True,
                "input_prefix": html_s[: _executor_mod().STRING_TRUNC_RESOLVED_PREFIX_LEN],
                "text_blocks_count": len(out_data.get("text_blocks") or []),
                "links_count": len(out_data.get("links") or []),
                "granularity": granularity,
                "content_root_css": content_root_css,
            }
        if "segment_text_blocks" in out_data:
            ri["segment_count"] = len(out_data.get("segment_text_blocks") or [])

        return {
            "status": "ok",
            "output": DictionaryNodeOutput(node_id=node.id, data=dict(out_data)),
            "details": {"resolved_inputs": ri},
        }

    def _resolve_write_object_to_document_body_node(
        self,
        node: WriteObjectToDocumentBodyUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "value", "type": "any", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["value"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        val = resolved.get("value")
        if val is None:
            return _executor_mod()._error_with_resolved_inputs(
                "Write object to document body: value is required.",
                dict(resolved),
            )
        if not isinstance(val, (dict, list)):
            return _executor_mod()._error_with_resolved_inputs(
                "Write object to document body: value must be a list or dictionary.",
                {**dict(resolved), "value_type": type(val).__name__},
            )
        text = deterministic_json_dumps(val)
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=text),
            "details": {"resolved_inputs": {"value_kind": "list" if isinstance(val, list) else "object"}},
        }

    def _resolve_append_value_to_document_node(
        self,
        node: AppendValueToDocumentUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "document", "type": "document", "value": None},
            {"key": "value", "type": "any", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["document", "value"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        try:
            d = self._document_plain_dict(resolved.get("document"))
            old = self._document_body_text(d)
        except ValueError as e:
            return _executor_mod()._error_with_resolved_inputs(str(e), dict(resolved))
        val = resolved.get("value")
        if val is None:
            return {
                "status": "error",
                "error": "Append value to document: value is required.",
                "details": {"resolved_inputs": {"text_chars": len(old)}},
            }
        if isinstance(val, (dict, list)):
            chunk = deterministic_json_dumps(val)
        else:
            chunk = str(val)
        sep = "\n\n"
        new_body = chunk if not old else old + sep + chunk
        return {
            "status": "ok",
            "output": StringNodeOutput(node_id=node.id, text=new_body),
            "details": {
                "resolved_inputs": {
                    "prior_chars": len(old),
                    "appended_chars": len(chunk),
                }
            },
        }

    def _resolve_validate_against_structure_node(
        self,
        node: ValidateAgainstStructureUtilityNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_inputs = (node.data or {}).get("required_inputs") or [
            {"key": "value", "type": "any", "value": None},
            {"key": "structure", "type": "structure", "value": None},
        ]
        resolved = _resolve_inputs_by_target_handle(
            node.id,
            ["value", "structure"],
            edges,
            outputs,
            input_overrides,
            raw_inputs,
        )
        val = resolved.get("value")
        schema_dict: Optional[Dict[str, Any]] = None
        structure_id_raw = (node.data or {}).get("structure_id")
        if structure_id_raw:
            try:
                sid = (
                    UUID(str(structure_id_raw).strip()) if not isinstance(structure_id_raw, UUID) else structure_id_raw
                )
                structure = self.session.exec(
                    select(Structure).where(
                        col(Structure.id) == sid,
                        or_(col(Structure.user_id) == self.user_id, col(Structure.user_id).is_(None)),
                    )
                ).first()
                if structure:
                    try:
                        schema_dict = json.loads(structure.json_schema)
                    except json.JSONDecodeError as e:
                        return {
                            "status": "error",
                            "error": f"Validate against structure: invalid JSON schema ({e})",
                            "details": {"resolved_inputs": {"structure_id": str(sid)}},
                        }
            except (ValueError, TypeError):
                return {
                    "status": "error",
                    "error": "Validate against structure: invalid structure_id.",
                    "details": {"resolved_inputs": {"structure_id": structure_id_raw}},
                }

        if schema_dict is None:
            st = resolved.get("structure")
            if isinstance(st, dict):
                schema_dict = st
            elif isinstance(st, StructureNodeOutput):
                schema_dict = dict(st.schema_dict) if st.schema_dict else None

        if not schema_dict:
            return _executor_mod()._error_with_resolved_inputs(
                "Validate against structure: provide structure_id on the node or wire a Structure output.",
                dict(resolved),
            )

        instance = val
        if instance is None:
            return _executor_mod()._error_with_resolved_inputs(
                "Validate against structure: value is required.",
                dict(resolved),
            )

        try:
            Draft202012Validator(schema_dict).validate(instance)
        except ValidationError as e:
            return {
                "status": "error",
                "error": f"Validate against structure: {e.message}",
                "details": {
                    "resolved_inputs": {
                        "failed_path": list(e.path) if e.path else [],
                    }
                },
            }

        if isinstance(instance, dict):
            out: NodeOutputUnion = DictionaryNodeOutput(node_id=node.id, data=dict(instance))
        elif isinstance(instance, list):
            out = ListNodeOutput(node_id=node.id, data=list(instance))
        elif isinstance(instance, bool):
            out = BooleanNodeOutput(node_id=node.id, value=instance)
        elif isinstance(instance, int) and not isinstance(instance, bool):
            out = IntNodeOutput(node_id=node.id, value=int(instance))
        elif isinstance(instance, str):
            out = StringNodeOutput(node_id=node.id, text=instance)
        else:
            out = StringNodeOutput(node_id=node.id, text=json.dumps(instance, ensure_ascii=False))
        return {
            "status": "ok",
            "output": out,
            "details": {"resolved_inputs": {"validated": True}},
        }

    def _resolve_start_node(self, node: StartGraphNode, input_overrides: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return StartNodeOutput from required_inputs (or legacy data.text).
        Uses input_overrides for null values.

        - raw_inputs is None: legacy path (data.text or input_overrides)
        - raw_inputs == []: no inputs; single output handle "output" with empty string
        - else: process each required input
        """
        raw_inputs = node.data.get("required_inputs")
        if raw_inputs is None:
            # Legacy: data.text as single string input
            text = node.data.get("text", "") or input_overrides.get("text", "") or input_overrides.get("user_input", "")
            legacy_outputs = {"user_input": text}
            return {
                "status": "ok",
                "output": StartNodeOutput(node_id=node.id, outputs=legacy_outputs, text=text),
                "details": {"resolved_inputs": {"user_input": text}},
            }
        if isinstance(raw_inputs, list) and len(raw_inputs) == 0:
            # Explicit no inputs: single output handle for wiring
            return {
                "status": "ok",
                "output": StartNodeOutput(node_id=node.id, outputs={"output": ""}, text=""),
                "details": {"resolved_inputs": {"output": ""}},
            }

        outputs_dict: Dict[str, Any] = {}
        text_parts: List[str] = []

        for item in raw_inputs:
            if isinstance(item, dict):
                key = item.get("key", "")
                inp_type = item.get("type", "string")
                val = item.get("value")
                if (
                    val is None
                    or (inp_type == "string" and val == "")
                    or (inp_type == "datetime" and (val is None or (isinstance(val, str) and not str(val).strip())))
                ):
                    val = input_overrides.get(key)
                if inp_type == "any":
                    if val is None:
                        return _executor_mod()._error_with_resolved_inputs(
                            f"Start node required input '{key}' has no value and no override.",
                            {**dict(outputs_dict), "_missing_key": key},
                        )
                elif val is None and inp_type == "string":
                    val = ""
                elif val is None and inp_type == "boolean":
                    val = False
                elif val is None and inp_type == "int":
                    val = 0
                elif inp_type == "datetime" and val is not None:
                    norm = parse_rfc3339_datetime_string(str(val))
                    if norm is None:
                        return _executor_mod()._error_with_resolved_inputs(
                            f"Start node required input '{key}' is not a valid RFC3339 datetime.",
                            {**dict(outputs_dict), key: val},
                        )
                    val = norm
                if inp_type == "gmail" and val is not None:
                    if not isinstance(val, dict):
                        return _executor_mod()._error_with_resolved_inputs(
                            f"Start node required input '{key}' must be a JSON object for type gmail.",
                            {**dict(outputs_dict), key: val},
                        )
                    val = gmail_dict_to_node_output(node.id, val)
                if val is None:
                    return _executor_mod()._error_with_resolved_inputs(
                        f"Start node required input '{key}' has no value and no override.",
                        {**dict(outputs_dict), "_missing_key": key},
                    )
                outputs_dict[key] = val
                if isinstance(val, str):
                    text_parts.append(val)
                elif isinstance(val, (list, dict)):
                    text_parts.append(json.dumps(val, indent=2))
                elif isinstance(val, (bool, int)):
                    text_parts.append(str(val))
                elif isinstance(val, float):
                    text_parts.append(str(val))
                else:
                    text_parts.append(str(val))
            else:
                continue

        text = "\n\n".join(text_parts)
        return {
            "status": "ok",
            "output": StartNodeOutput(node_id=node.id, outputs=outputs_dict, text=text),
            "details": {"resolved_inputs": dict(outputs_dict)},
        }

    async def _resolve_workflow_node(
        self,
        node: WorkflowRefNode,
        edges: List[GraphEdge],
        outputs: Dict[str, NodeOutputUnion],
        input_overrides: Dict[str, Any],
        parent_workflow: Optional[WorkflowDefinition],
        execution_stack: frozenset,
        execution_time_zone: Optional[str] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the referenced sub-workflow. Build input_overrides from parent edges.
        Reject self-reference and cycles.
        """
        parent_ov = dict(input_overrides or {})
        workflow_id_raw = node.data.get("workflow_id")
        if not workflow_id_raw:
            return {
                "status": "error",
                "error": f"Workflow node '{node.id}' has no workflow_id.",
                "details": {"resolved_inputs": {"input_overrides": parent_ov}},
            }
        try:
            sub_wf_id = UUID(workflow_id_raw) if isinstance(workflow_id_raw, str) else workflow_id_raw
        except (ValueError, TypeError):
            return {
                "status": "error",
                "error": f"Workflow node '{node.id}' has invalid workflow_id.",
                "details": {"resolved_inputs": {"input_overrides": parent_ov}},
            }

        if parent_workflow and sub_wf_id == parent_workflow.id:
            return {
                "status": "error",
                "error": f"Workflow node '{node.id}' references itself (self-reference not allowed).",
                "details": {"resolved_inputs": {"input_overrides": parent_ov}},
            }
        if sub_wf_id in execution_stack:
            return {
                "status": "error",
                "error": f"Workflow node '{node.id}' creates a cycle (workflow {sub_wf_id} already in execution stack).",
                "details": {"resolved_inputs": {"input_overrides": parent_ov}},
            }

        new_stack = execution_stack | (frozenset({parent_workflow.id}) if parent_workflow else frozenset())
        depth_limits = getattr(self, "_resolved_execution_limits", None)
        if depth_limits is not None and len(new_stack) > depth_limits.max_nested_depth:
            return {
                "status": "error",
                "error": (
                    f"Nested workflow depth exceeds maximum ({depth_limits.max_nested_depth}) "
                    f"for workflow node '{node.id}'."
                ),
                "details": {"resolved_inputs": {"input_overrides": parent_ov}},
            }

        sub_wf = WorkflowDefinitionService(self.session, self.user_id).get_workflow(sub_wf_id)
        if not sub_wf:
            return {
                "status": "error",
                "error": f"Workflow node '{node.id}' references workflow {sub_wf_id} which was not found.",
                "details": {"resolved_inputs": {"input_overrides": parent_ov}},
            }

        overrides: Dict[str, Any] = dict(input_overrides or {})
        for edge in edges:
            if edge.target != node.id:
                continue
            key = edge.target_handle or "user_input"
            src_out = outputs.get(edge.source)
            if src_out is None:
                continue
            slot = _get_slot_value(src_out, edge.source_handle)
            overrides[key] = node_output_to_input_override_value(slot)

        nested_ov = filter_output_overrides_for_graph(sub_wf.graph, output_overrides_map or {})
        executor = _executor_mod().WorkflowExecutor(
            self.session,
            self.user_id,
            default_google_workflow_connection_id=self.default_google_workflow_connection_id,
        )
        result = await executor.run(
            sub_wf,
            input_overrides=overrides,
            output_overrides_map=nested_ov,
            execution_stack=new_stack,
            execution_time_zone=execution_time_zone,
            execution_limits=getattr(self, "_resolved_execution_limits", None),
        )

        if result.status != "ok":
            failed = next((r for r in result.node_results if r.status == "error"), None)
            err_msg = failed.error if failed else f"Sub-workflow {sub_wf_id} failed with status {result.status}"
            sub_nodes = sub_wf.graph.get("nodes", [])
            node_id_to_label = {
                n["id"]: (n.get("label") or n.get("data", {}).get("label") or n["id"]) for n in sub_nodes
            }
            return {
                "status": "error",
                "error": err_msg,
                "details": {
                    "sub_workflow_id": str(sub_wf_id),
                    "sub_workflow_name": sub_wf.name,
                    "sub_workflow_node_results": [r.model_dump(mode="json") for r in result.node_results],
                    "sub_workflow_node_labels": node_id_to_label,
                    "resolved_inputs": {"input_overrides": dict(overrides)},
                },
            }

        wf_input_details: Dict[str, Any] = {"resolved_inputs": {"input_overrides": dict(overrides)}}

        stop_output_type = "string"
        sub_nodes = sub_wf.graph.get("nodes", [])
        stop_node_ids = [n["id"] for n in sub_nodes if n.get("kind") == "stop"]
        for n in sub_nodes:
            if n.get("kind") == "stop":
                req = (n.get("data") or {}).get("required_outputs") or [{"key": "output", "type": "string"}]
                stop_output_type = (req[0] or {}).get("type", "string") if req else "string"
                break

        stop_raw: NodeOutputUnion = StopNodeOutput(node_id="", text="")
        for nr in result.node_results:
            if nr.node_id in stop_node_ids and nr.output:
                stop_raw = nr.output
                break

        return {
            "status": "ok",
            "output": _executor_mod().coerce_stop_output(node.id, stop_output_type, stop_raw),
            "details": wf_input_details,
        }

    def _resolve_stop_node(self, node: StopGraphNode, upstream: list[NodeOutputUnion]) -> Dict[str, Any]:
        """Use a single upstream output as the final Stop output.

        Originally the Stop node returned only the last thing provided. When multiple
        edges connect to Stop (e.g. legacy Start->Stop plus List->Stop), concatenating
        all upstream would prepend stray output. We prefer the last upstream that
        matches the Stop's required_outputs type; otherwise use the last upstream.
        """
        req_outputs = node.data.get("required_outputs") or [{"key": "output", "type": "string"}]
        expected_type = (req_outputs[0] or {}).get("type", "string") if req_outputs else "string"
        if not upstream:
            return {
                "status": "ok",
                "output": _executor_mod().coerce_stop_output(
                    node.id, expected_type, StopNodeOutput(node_id=node.id, text="")
                ),
                "details": {
                    "resolved_inputs": {
                        "upstream_output": None,
                        "expected_output_type": expected_type,
                    }
                },
            }

        def _matches_type(o: NodeOutputUnion) -> bool:
            if expected_type == "any":
                return True
            if expected_type == "list":
                if isinstance(o, ListNodeOutput):
                    return True
                if isinstance(o, DictionaryNodeOutput):
                    return isinstance(o.data.get("messages"), list)
                return False
            if expected_type == "dictionary":
                return isinstance(o, DictionaryNodeOutput)
            if expected_type == "boolean":
                return isinstance(o, BooleanNodeOutput)
            if expected_type == "int":
                return isinstance(o, IntNodeOutput)
            if expected_type == "datetime":
                return isinstance(o, DateTimeNodeOutput)
            if expected_type == "structure":
                return isinstance(o, StructureNodeOutput)
            if expected_type == "document":
                return isinstance(o, DocumentNodeOutput)
            if expected_type == "gmail":
                return isinstance(o, GmailNodeOutput)
            return isinstance(o, (StringNodeOutput, ResponseNodeOutput, StartNodeOutput))

        out = upstream[-1]
        for o in reversed(upstream):
            if _matches_type(o):
                out = o
                break

        return {
            "status": "ok",
            "output": _executor_mod().coerce_stop_output(node.id, expected_type, out),
            "details": {
                "resolved_inputs": {
                    "upstream_output": _executor_mod()._node_output_to_json_dict(out),
                    "expected_output_type": expected_type,
                }
            },
        }
