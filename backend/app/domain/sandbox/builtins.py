"""Stable ids for built-in sandbox workflows (must match Alembic seed)."""

import uuid

STARTER_SANDBOX_WORKFLOW_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "mindweave.sandbox.starter_behavior.v1")
EMPTY_SANDBOX_BOARD_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "mindweave.sandbox.empty_board.v1")
