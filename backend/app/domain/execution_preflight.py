"""Static execution-budget preflight for workflow runs.

Hard rejects (no override) only when a defensible upper bound on logged node steps
already exceeds ``max_node_executions``. When the bound depends on unknown loop lists,
returns warnings that require ``acknowledge_preflight_warnings`` on the run request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.domain.execution_limits import ResolvedExecutionLimits
from app.domain.schemas import ForLoopControlNode, GraphEdge, ListPrimitiveNode, TryCatchControlNode, WorkflowRefNode
from app.domain.workflow_executor.graph import (
    _detect_cycle,
    validate_for_loop_bodies,
    validate_for_loop_end_configuration,
    validate_parallel_for_loop_no_nested_loop,
    validate_try_catch_regions,
)
from app.domain.workflow_executor.parsing import _parse_node


def _edges_for_global_cycle_detection(edges: list[GraphEdge], nodes_by_id: dict[str, Any]) -> list[GraphEdge]:
    out: list[GraphEdge] = []
    for e in edges:
        tgt = nodes_by_id.get(e.target)
        if isinstance(tgt, TryCatchControlNode) and (e.target_handle or "").strip() == "value":
            continue
        out.append(e)
    return out


def _parse_nodes_and_edges(graph: dict[str, Any]) -> tuple[dict[str, Any], list[GraphEdge]]:
    nodes_by_id: dict[str, Any] = {}
    for raw_node in graph.get("nodes") or []:
        parsed = _parse_node(raw_node if isinstance(raw_node, dict) else {})
        if parsed is not None:
            nodes_by_id[parsed.id] = parsed
    edges = [GraphEdge(**e) for e in (graph.get("edges") or []) if isinstance(e, dict)]
    return nodes_by_id, edges


def _for_loop_list_source_ids(loop_id: str, edges: Iterable[GraphEdge]) -> list[str]:
    srcs: list[str] = []
    for e in edges:
        if e.target != loop_id:
            continue
        th = (e.target_handle or "").strip() or "input"
        if th == "input":
            srcs.append(e.source)
    return srcs


def _static_list_length_if_known(loop_id: str, edges: list[GraphEdge], nodes_by_id: dict[str, Any]) -> tuple[int | None, bool]:
    """Return (length, certain) for the For Loop list input; certain False when not a list primitive."""
    srcs = _for_loop_list_source_ids(loop_id, edges)
    if len(srcs) != 1:
        return None, False
    src = nodes_by_id.get(srcs[0])
    if isinstance(src, ListPrimitiveNode):
        return len(src.data or []), True
    return None, False


def _for_loop_iteration_upper(
    loop_id: str,
    node: ForLoopControlNode,
    edges: list[GraphEdge],
    nodes_by_id: dict[str, Any],
    eff: ResolvedExecutionLimits,
) -> tuple[int, bool]:
    """Upper bound on iterations for this loop in the worst static case."""
    ceiling = eff.max_loop_iterations
    raw_cap = (node.data or {}).get("max_iterations")
    node_cap: int | None = None
    if raw_cap is not None:
        try:
            node_cap = max(1, int(raw_cap))
        except (TypeError, ValueError):
            node_cap = None
    list_len, list_certain = _static_list_length_if_known(loop_id, edges, nodes_by_id)
    uncertain = not list_certain

    if list_len is not None:
        upper = min(list_len, ceiling)
    else:
        upper = ceiling
    if node_cap is not None:
        upper = min(upper, node_cap)
    return max(0, upper), uncertain


def _loop_product_for_node(
    nid: str,
    fl_bodies: dict[str, set[str]],
    iter_counts: dict[str, int],
) -> int:
    """Product of iteration counts for every For Loop whose body contains ``nid`` (may be 0)."""
    m = 1
    for lid, body in fl_bodies.items():
        if nid in body:
            m *= iter_counts.get(lid, 1)
    return m


@dataclass(frozen=True)
class ExecutionPreflightResult:
    estimated_max_node_executions: int
    max_node_executions: int
    uncertain_loop_lists: bool
    skipped_nested_workflows: bool
    hard_block_message: str | None
    warnings: list[dict[str, Any]]
    requires_acknowledgement: bool

    @property
    def ok_without_ack(self) -> bool:
        return self.hard_block_message is None and not self.requires_acknowledgement


def evaluate_execution_preflight(
    graph: dict[str, Any],
    eff: ResolvedExecutionLimits,
    *,
    acknowledge_preflight_warnings: bool = False,
) -> ExecutionPreflightResult:
    """Analyze graph; set ``requires_acknowledgement`` when user must acknowledge advisory warnings."""

    nodes_by_id, edges = _parse_nodes_and_edges(graph)
    cycle = _detect_cycle(list(nodes_by_id.keys()), _edges_for_global_cycle_detection(edges, nodes_by_id))
    if cycle:
        raise ValueError(f"Workflow graph contains a cycle involving nodes: {cycle}")
    try:
        fl_bodies = validate_for_loop_bodies(nodes_by_id, edges)
        validate_for_loop_end_configuration(nodes_by_id, edges)
        validate_parallel_for_loop_no_nested_loop(nodes_by_id, edges)
        validate_try_catch_regions(nodes_by_id, edges)
    except ValueError:
        raise

    iter_counts: dict[str, int] = {}
    uncertain_loop = False
    for lid, node in nodes_by_id.items():
        if not isinstance(node, ForLoopControlNode):
            continue
        up, unc = _for_loop_iteration_upper(lid, node, edges, nodes_by_id, eff)
        iter_counts[lid] = up
        uncertain_loop = uncertain_loop or unc

    skipped_nested = any(isinstance(n, WorkflowRefNode) for n in nodes_by_id.values())

    total = 0
    for nid in nodes_by_id:
        total += _loop_product_for_node(nid, fl_bodies, iter_counts)

    warnings: list[dict[str, Any]] = []
    if uncertain_loop:
        warnings.append(
            {
                "code": "loop_iteration_uncertain",
                "message": (
                    "One or more For Loops take their list from runtime data. "
                    "A conservative iteration ceiling was used for budgeting; actual runs may differ."
                ),
            }
        )
    if skipped_nested:
        warnings.append(
            {
                "code": "nested_workflow_not_estimated",
                "message": "This graph contains nested workflow nodes; static budgeting does not include subgraph cost.",
            }
        )

    hard: str | None = None
    requires_ack = False

    if total > eff.max_node_executions:
        if uncertain_loop or skipped_nested:
            requires_ack = True
        else:
            hard = (
                f"Static execution budget estimate ({total} node steps) exceeds "
                f"max_node_executions ({eff.max_node_executions}) for this run."
            )

    if requires_ack and acknowledge_preflight_warnings:
        requires_ack = False

    return ExecutionPreflightResult(
        estimated_max_node_executions=total,
        max_node_executions=eff.max_node_executions,
        uncertain_loop_lists=uncertain_loop,
        skipped_nested_workflows=skipped_nested,
        hard_block_message=hard,
        warnings=warnings,
        requires_acknowledgement=requires_ack,
    )


def preflight_http_detail(
    res: ExecutionPreflightResult,
) -> dict[str, Any]:
    """Structured FastAPI ``HTTPException(detail=...)`` payload for preflight outcomes."""
    if res.hard_block_message:
        return {
            "error": "preflight_blocked",
            "message": res.hard_block_message,
            "estimated_max_node_executions": res.estimated_max_node_executions,
            "max_node_executions": res.max_node_executions,
        }
    if res.requires_acknowledgement:
        return {
            "error": "preflight_warnings",
            "message": (
                "This run may exceed safe execution limits or uses uncertain static estimates. "
                "Confirm in the editor and retry with acknowledge_preflight_warnings: true to proceed."
            ),
            "warnings": res.warnings,
            "estimated_max_node_executions": res.estimated_max_node_executions,
            "max_node_executions": res.max_node_executions,
        }
    raise RuntimeError("preflight_http_detail called with no error to report")
