from collections import defaultdict, deque
from typing import Any, Dict, Optional

from app.domain.schemas import (
    BasicConditionalControlNode,
    BetweenControlNode,
    ForLoopControlNode,
    ForLoopEndControlNode,
    GraphEdge,
    GtControlNode,
    GteControlNode,
    IsControlNode,
    IsEmptyControlNode,
    LtControlNode,
    LteControlNode,
    TryCatchControlNode,
)


def _for_loop_end_ids(nodes_by_id: dict[str, Any]) -> set[str]:
    return {nid for nid, n in nodes_by_id.items() if isinstance(n, ForLoopEndControlNode)}


def _detect_cycle(node_ids: list[str], edges: list[GraphEdge]) -> Optional[list[str]]:
    """
    Kahn's algorithm for cycle detection.
    Returns a list of node IDs involved in the cycle, or None if acyclic.
    """
    in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
    adjacency: Dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        adjacency[edge.source].append(edge.target)
        in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

    queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
    visited = 0

    while queue:
        node = queue.popleft()
        visited += 1
        for neighbour in adjacency[node]:
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    if visited != len(node_ids):
        # Nodes with remaining in-degree > 0 are in a cycle.
        return [nid for nid, deg in in_degree.items() if deg > 0]
    return None


def _topological_order(node_ids: list[str], edges: list[GraphEdge]) -> list[str]:
    """
    Return node IDs in topological order (Kahn's algorithm).
    Assumes the graph has already been validated as acyclic.
    """
    in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
    adjacency: Dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        adjacency[edge.source].append(edge.target)
        in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

    queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
    order: list[str] = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbour in adjacency[node]:
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                queue.append(neighbour)

    return order


def _build_in_degree_and_adjacency(
    node_ids: list[str],
    edges: list[GraphEdge],
    nodes_by_id: Optional[Dict[str, Any]] = None,
) -> tuple[Dict[str, int], Dict[str, list[str]]]:
    """
    Build in-degree (incoming edge count) and adjacency (source -> [targets]) for level-based execution.
    For conditionals: nodes that have incoming edges from both branches of the same conditional
    only count 1 toward in_degree (since only one branch runs).
    """
    in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
    adjacency: Dict[str, list[str]] = defaultdict(list)
    nodes_by_id = nodes_by_id or {}

    # Find conditional nodes and build reachability: for each conditional C, which nodes are
    # reachable from C via true handle, and which via false handle.
    cond_true_descendants: Dict[str, set[str]] = {}
    cond_false_descendants: Dict[str, set[str]] = {}
    for nid, node in nodes_by_id.items():
        if isinstance(
            node,
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
        ):
            true_set: set[str] = set()
            false_set: set[str] = set()
            for e in edges:
                if e.source != nid:
                    continue
                if e.source_handle == "true":
                    true_set.add(e.target)
                elif e.source_handle == "false":
                    false_set.add(e.target)
            # Expand transitively
            changed = True
            while changed:
                changed = False
                for e in edges:
                    if e.source in true_set and e.target not in true_set:
                        true_set.add(e.target)
                        changed = True
                    if e.source in false_set and e.target not in false_set:
                        false_set.add(e.target)
                        changed = True
            cond_true_descendants[nid] = true_set
            cond_false_descendants[nid] = false_set

    # For each target N, track which conditionals have contributed to its in_degree.
    cond_contributed: Dict[str, set[str]] = defaultdict(set)

    for edge in edges:
        adjacency[edge.source].append(edge.target)
        target = edge.target
        source = edge.source

        # Check if source is a descendant of any conditional's branch.
        # If so, add at most 1 per conditional to target's in_degree.
        from_conditional = False
        for cond_id, true_set in cond_true_descendants.items():
            if source in true_set:
                if cond_id not in cond_contributed[target]:
                    in_degree[target] += 1
                    cond_contributed[target].add(cond_id)
                from_conditional = True
                break
        if not from_conditional:
            for cond_id, false_set in cond_false_descendants.items():
                if source in false_set:
                    if cond_id not in cond_contributed[target]:
                        in_degree[target] += 1
                        cond_contributed[target].add(cond_id)
                    from_conditional = True
                    break
        if not from_conditional:
            in_degree[target] += 1

    return in_degree, adjacency


def _for_loop_iteration_seed_targets(for_loop_id: str, edges: list[GraphEdge], for_loop_end_ids: set[str]) -> set[str]:
    seeds: set[str] = set()
    for e in edges:
        if e.source != for_loop_id:
            continue
        if e.target in for_loop_end_ids:
            continue
        sh = e.source_handle or ""
        th = e.target_handle or ""
        if sh == "signal_out" and th == "trigger":
            seeds.add(e.target)
        elif sh == "item":
            seeds.add(e.target)
    return seeds


def _forward_closure_from_seeds(
    seeds: set[str],
    edges: list[GraphEdge],
    banned: set[str],
    for_loop_end_ids: set[str],
) -> set[str]:
    result: set[str] = set()
    queue: deque[str] = deque()
    for s in seeds:
        if s in banned or s in for_loop_end_ids:
            continue
        result.add(s)
        queue.append(s)
    while queue:
        u = queue.popleft()
        for e in edges:
            if e.source != u:
                continue
            v = e.target
            if v in banned or v in for_loop_end_ids:
                continue
            if v not in result:
                result.add(v)
                queue.append(v)
    return result


def for_loop_body_node_ids(for_loop_id: str, edges: list[GraphEdge], nodes_by_id: dict[str, Any]) -> set[str]:
    """Nodes in the loop body: forward closure from item/signal iteration roots, excluding the For Loop node.

    For Loop End nodes are never part of the body (boundary + export targets).
    """
    end_ids = _for_loop_end_ids(nodes_by_id)
    seeds = _for_loop_iteration_seed_targets(for_loop_id, edges, end_ids)
    return _forward_closure_from_seeds(seeds, edges, {for_loop_id}, end_ids)


def validate_for_loop_bodies(nodes_by_id: dict[str, Any], edges: list[GraphEdge]) -> dict[str, set[str]]:
    """
    Map for_loop_node_id -> body node ids. Raises ValueError if two loops share body
    nodes without one loop nesting inside the other.
    """
    fl_ids = [nid for nid, n in nodes_by_id.items() if isinstance(n, ForLoopControlNode)]
    id_to_body: dict[str, set[str]] = {fid: for_loop_body_node_ids(fid, edges, nodes_by_id) for fid in fl_ids}
    ids = list(id_to_body.keys())
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            ba, bb = id_to_body[a], id_to_body[b]
            inter = ba & bb
            if not inter:
                continue
            nested_ok = a in bb or b in ba
            if not nested_ok:
                raise ValueError(
                    f"For Loop nodes '{a}' and '{b}' have overlapping loop bodies {sorted(inter)}; "
                    "nest one loop inside the other or separate body regions."
                )
    return id_to_body


def validate_parallel_for_loop_no_nested_loop(nodes_by_id: dict[str, Any], edges: list[GraphEdge]) -> None:
    """Parallel / batched for-loops must not contain another For Loop in the body (v1)."""
    for fid, node in nodes_by_id.items():
        if not isinstance(node, ForLoopControlNode):
            continue
        data = node.data or {}
        legacy_parallel = bool(data.get("parallel_iterations"))
        raw_mode = (data.get("iteration_mode") or "sequential")
        mode = raw_mode.strip().lower() if isinstance(raw_mode, str) else str(raw_mode).lower()
        concurrent = legacy_parallel or mode in ("parallel", "batched")
        if not concurrent:
            continue
        body = for_loop_body_node_ids(fid, edges, nodes_by_id)
        for bid in body:
            if isinstance(nodes_by_id.get(bid), ForLoopControlNode):
                raise ValueError(
                    f"For Loop '{fid}' uses parallel/batched iterations but its body contains "
                    f"nested For Loop '{bid}'; unsupported in v1."
                )


def validate_for_loop_end_configuration(nodes_by_id: dict[str, Any], edges: list[GraphEdge]) -> None:
    """
    For Loop End nodes must declare data.for_loop_id, have a trigger edge from that For Loop,
    and each export edge must land on a unique target_handle (dict key) with source in the paired body.
    """
    for eid, node in nodes_by_id.items():
        if not isinstance(node, ForLoopEndControlNode):
            continue
        fl_id = (node.data or {}).get("for_loop_id")
        if not fl_id or not isinstance(fl_id, str):
            raise ValueError(f"For Loop End node '{eid}' requires data.for_loop_id (paired For Loop node id).")
        fl = nodes_by_id.get(fl_id)
        if not isinstance(fl, ForLoopControlNode):
            raise ValueError(f"For Loop End '{eid}' data.for_loop_id must reference a For Loop control node.")

        trigger_ok = any(
            e.source == fl_id
            and e.target == eid
            and (e.source_handle or "") == "signal_out"
            and (e.target_handle or "") == "trigger"
            for e in edges
        )
        if not trigger_ok:
            raise ValueError(
                f"For Loop End '{eid}' must have an edge from For Loop '{fl_id}' "
                "with source_handle signal_out to target_handle trigger."
            )

        body = for_loop_body_node_ids(fl_id, edges, nodes_by_id)
        export_edges = [e for e in edges if e.target == eid and (e.target_handle or "") != "trigger"]
        if not export_edges:
            raise ValueError(
                f"For Loop End '{eid}' requires at least one export edge (data input with a named target_handle)."
            )
        seen_keys: set[str] = set()
        for e in export_edges:
            key = (e.target_handle or "").strip()
            if not key:
                raise ValueError(
                    f"For Loop End '{eid}' export from '{e.source}' must use a non-empty target_handle as the key."
                )
            if key in seen_keys:
                raise ValueError(f"For Loop End '{eid}' duplicate export key '{key}'.")
            seen_keys.add(key)
            if e.source not in body:
                raise ValueError(
                    f"For Loop End '{eid}' export '{key}' source '{e.source}' must lie inside "
                    f"the body of For Loop '{fl_id}'."
                )


def try_catch_try_seeds(tc_id: str, edges: list[GraphEdge]) -> set[str]:
    return {e.target for e in edges if e.source == tc_id and (e.source_handle or "") == "try"}


def try_catch_catch_seeds(tc_id: str, edges: list[GraphEdge]) -> set[str]:
    return {e.target for e in edges if e.source == tc_id and (e.source_handle or "") == "catch"}


def try_catch_try_region(tc_id: str, edges: list[GraphEdge]) -> set[str]:
    seeds = try_catch_try_seeds(tc_id, edges)
    return _forward_closure_from_seeds(seeds, edges, {tc_id}, frozenset())


def try_catch_catch_region(tc_id: str, edges: list[GraphEdge]) -> set[str]:
    seeds = try_catch_catch_seeds(tc_id, edges)
    return _forward_closure_from_seeds(seeds, edges, {tc_id}, frozenset())


def validate_try_catch_regions(nodes_by_id: dict[str, Any], edges: list[GraphEdge]) -> dict[str, tuple[set[str], set[str]]]:
    """Return try_catch_node_id -> (try_region, catch_region); raises ValueError on invalid semantics."""
    tc_ids = sorted(nid for nid, n in nodes_by_id.items() if isinstance(n, TryCatchControlNode))
    reg: dict[str, tuple[set[str], set[str]]] = {}
    for tid in tc_ids:
        t_seeds = try_catch_try_seeds(tid, edges)
        if not t_seeds:
            raise ValueError(f"Try/Catch node '{tid}' must have at least one outgoing edge with source_handle 'try'.")
        tr = try_catch_try_region(tid, edges)
        csr = try_catch_catch_seeds(tid, edges)
        cr: set[str] = try_catch_catch_region(tid, edges) if csr else set()
        inter = tr & cr
        if inter:
            raise ValueError(
                f"Try/Catch '{tid}' has overlapping try and catch regions ({sorted(inter)}); "
                "keep branches disjoint until after the node's output handle merges downstream."
            )
        reg[tid] = (tr, cr)
    ids = list(reg.keys())
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            ta, ca = reg[a]
            tb, cb = reg[b]
            union_a = ta | ca
            union_b = tb | cb
            inter_nodes = union_a & union_b
            if not inter_nodes:
                continue
            nested_ok = a in union_b or b in union_a
            if nested_ok:
                continue
            raise ValueError(
                f"Try/Catch nodes '{a}' and '{b}' overlap on {sorted(inter_nodes)}; nest one Try/Catch inside "
                "the other's branch or separate regions."
            )
    return reg


def union_try_catch_interior_nodes(reg: dict[str, tuple[set[str], set[str]]]) -> set[str]:
    out: set[str] = set()
    for tr, cr in reg.values():
        out |= tr | cr
    return out


def main_schedule_node_ids(all_ids: set[str], union_loop_body: set[str]) -> set[str]:
    return all_ids - union_loop_body


def edges_with_both_endpoints_in(node_ids: set[str], edges: list[GraphEdge]) -> list[GraphEdge]:
    return [e for e in edges if e.source in node_ids and e.target in node_ids]
