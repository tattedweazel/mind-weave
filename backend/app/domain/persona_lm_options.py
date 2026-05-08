"""Map Persona settings to LM Studio OpenAI-compatible chat/completions extra fields."""

from typing import Any

from app.persistence.tables import Persona


def persona_lm_chat_options(persona: Persona | None) -> dict[str, Any]:
    """Extra JSON fields for POST …/v1/chat/completions when the Persona opts out of extended thinking.

    LM Studio 0.4.8+ documents ``reasoning_effort`` / ``reasoning_tokens`` on the OpenAI-compatible endpoint.
    """
    if persona is None or not persona.suppress_lm_thinking:
        return {}
    return {"reasoning_effort": "none"}
