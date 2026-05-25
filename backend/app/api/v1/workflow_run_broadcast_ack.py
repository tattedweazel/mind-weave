"""POST acknowledgement for a running workflow (Broadcast Message node)."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_user
from app.domain.workflow_executor.workflow_input_pending import (
    BroadcastAckWaitKey,
    complete_taken_broadcast_ack_wait,
    take_broadcast_ack_wait,
)
from app.persistence.db import get_session
from app.persistence.tables import User, WorkflowRun

router = APIRouter()


@router.post(
    "/workflow-runs/{run_id}/broadcast-ack",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def post_broadcast_ack_for_run(
    run_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    node_id: str = Form(..., min_length=1),
    for_loop_id: Optional[str] = Form(None),
    for_loop_iteration: int = Form(0),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    """Acknowledge a Broadcast Message modal to unblock the matching node during an async Build run."""
    run = session.get(WorkflowRun, run_id)
    if not run or run.started_by_user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    if (run.status or "") != "running":
        raise HTTPException(status_code=400, detail="Run is not active")

    key = BroadcastAckWaitKey(
        run_id=run_id,
        node_id=node_id,
        for_loop_id=(for_loop_id or "").strip() or None,
        iteration=int(for_loop_iteration),
    )
    fut = take_broadcast_ack_wait(key)
    if fut is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "No pending Broadcast Message step for this run/node "
                "(wrong node, loop context, or already acknowledged)"
            ),
        )

    async def deliver_ack_after_response() -> None:
        complete_taken_broadcast_ack_wait(fut)

    background_tasks.add_task(deliver_ack_after_response)
    return None
