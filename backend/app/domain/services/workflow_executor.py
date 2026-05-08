"""Compatibility facade: import `WorkflowExecutor` from the modular package."""

from app.domain.workflow_executor import WorkflowExecutor

__all__ = ["WorkflowExecutor"]
