"""Per-node concurrency classification for layered semaphores."""

from __future__ import annotations

from typing import Any, Literal

from app.domain.schemas import (
    AudioFileInputSkillNode,
    CalendarListEventsSkillNode,
    CaptureUrlSnapshotSkillNode,
    FetchUrlSkillNode,
    GmailListMessagesSkillNode,
    GoogleDocsGetDocumentSkillNode,
    MultimodalLLMCallSkillNode,
    SimpleLLMCallSkillNode,
    TextToSpeechSkillNode,
    TranscribeAudioSkillNode,
    TranscribeFileSkillNode,
    WorkflowRefNode,
)

ExtraKind = Literal["none", "llm", "browser", "external", "tts"]


def workflow_node_extra_concurrency_bucket(node: Any) -> ExtraKind:
    """Return which specialized semaphore complements the global node cap (mutex categories)."""
    if isinstance(node, (SimpleLLMCallSkillNode, MultimodalLLMCallSkillNode)):
        return "llm"
    if isinstance(node, CaptureUrlSnapshotSkillNode):
        return "browser"
    if isinstance(node, TextToSpeechSkillNode):
        return "tts"
    if isinstance(
        node,
        (
            FetchUrlSkillNode,
            TranscribeAudioSkillNode,
            AudioFileInputSkillNode,
            TranscribeFileSkillNode,
            GmailListMessagesSkillNode,
            CalendarListEventsSkillNode,
            GoogleDocsGetDocumentSkillNode,
            WorkflowRefNode,
        ),
    ):
        return "external"
    return "none"
