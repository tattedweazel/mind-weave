"""Workflow DAG execution (package). Public entry: `WorkflowExecutor`."""

from app.domain.workflow_executor.executor import WorkflowExecutor

__all__ = ["WorkflowExecutor"]
