"""Tests for persona → LM Studio chat completion extra fields."""

from app.domain.persona_lm_options import persona_lm_chat_options
from app.persistence.tables import Persona


def test_persona_lm_chat_options_empty_when_disabled():
    p = Persona(
        name="x",
        description="d",
        system_prompt="s",
        suppress_lm_thinking=False,
    )
    assert persona_lm_chat_options(p) == {}


def test_persona_lm_chat_options_reasoning_effort_none_when_enabled():
    p = Persona(
        name="x",
        description="d",
        system_prompt="s",
        suppress_lm_thinking=True,
    )
    assert persona_lm_chat_options(p) == {"reasoning_effort": "none"}


def test_persona_lm_chat_options_none_persona():
    assert persona_lm_chat_options(None) == {}
