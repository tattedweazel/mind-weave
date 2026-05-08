"""CapabilitySpec for workflow-backed Workspace capabilities (keys: ``wf:{uuid}``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional
from uuid import UUID


@dataclass(frozen=True)
class CapabilitySpec:
    capability_key: str
    display_name: str
    description: str
    backing: Literal["workflow", "inline"]
    workflow_id: Optional[UUID] = None
