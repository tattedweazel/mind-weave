"""Per-node concurrency classification for layered semaphores."""

from __future__ import annotations

from typing import Any, Literal

from app.domain.schemas import (
    AudioFileInputSkillNode,
    CalendarListEventsSkillNode,
    CaptureUrlSnapshotSkillNode,
    FetchUrlSkillNode,
    GmailListMessagesSkillNode,
    MultimodalLLMCallSkillNode,
    SimpleLLMCallSkillNode,
    TextToSpeechSkillNode,
    TranscribeAudioSkillNode,
    TranscribeFileSkillNode,
    WorkflowRefNode,
)

ExtraKind = Literal["none", "llm", "browser", "external"]


def workflow_node_extra_concurrency_bucket(node: Any) -> ExtraKind:
    """Return which specialized semaphore complements the global node cap (mutex categories)."""
    if isinstance(node, (SimpleLLMCallSkillNode, MultimodalLLMCallSkillNode)):
        return "llm"
    if isinstance(node, CaptureUrlSnapshotSkillNode):
        return "browser"
    if isinstance(
        node,
        (
            FetchUrlSkillNode,
            TextToSpeechSkillNode,
            TranscribeAudioSkillNode,
            AudioFileInputSkillNode,
            TranscribeFileSkillNode,
            GmailListMessagesSkillNode,
            CalendarListEventsSkillNode,
            WorkflowRefNode,
        ),
    ):
        return "external"
    return "none"
