from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.domain.schemas import GraphEdge, NodeOutputUnion
from app.persistence.tables import WorkflowDefinition


@dataclass
class ExecutionNodeContext:
    node_id: str
    node: Any
    upstream: list[NodeOutputUnion]
    edges: List[GraphEdge]
    outputs: Dict[str, NodeOutputUnion]
    input_overrides: Optional[Dict[str, Any]]
    workflow: Optional[WorkflowDefinition]
    execution_stack: Optional[frozenset]
    execution_time_zone: Optional[str]
    loop_list_carry: Optional[Dict[tuple[str, str], list[Any]]]
    for_loop_id: Optional[str]
    output_overrides_map: Optional[Dict[str, NodeOutputUnion]]
    stream_run_id: Optional[uuid.UUID]
    for_loop_iteration: Optional[int]
