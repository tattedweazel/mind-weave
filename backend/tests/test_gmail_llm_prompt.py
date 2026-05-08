"""Tests for Gmail → LLM user prompt slimming (headers + plain body; no label noise)."""

import json

from app.domain.workflow_executor.gmail_llm_prompt import (
    format_gmail_message_dict_for_llm_prompt,
    is_gmail_like_message_dict,
    slim_gmail_dict_for_llm_prompt,
    strip_invisible_email_text_for_llm,
)


def test_is_gmail_like_message_dict_positive():
    assert is_gmail_like_message_dict(
        {"id": "a", "threadId": "b", "from": "x", "labelIds": ["INBOX"]}
    )
    assert is_gmail_like_message_dict(
        {"subject": "Hi", "body_text": "Hello", "from": "a@b.com"},
    )


def test_is_gmail_like_message_dict_negative():
    assert not is_gmail_like_message_dict({})
    assert not is_gmail_like_message_dict({"foo": "bar"})
    assert not is_gmail_like_message_dict(None)


def test_slim_gmail_dict_drops_noise_and_snippet_when_body():
    d = {
        "id": "m1",
        "threadId": "t1",
        "subject": "S",
        "from": "a@x.com",
        "to": "b@y.com",
        "date": "Mon, 1 Jan 2024 00:00:00 +0000",
        "labelIds": ["INBOX", "UNREAD"],
        "internalDate": "123",
        "snippet": "short",
        "body_text": "Plain body here",
        "body_truncated": True,
    }
    slim = slim_gmail_dict_for_llm_prompt(d)
    assert slim == {
        "id": "m1",
        "threadId": "t1",
        "subject": "S",
        "from": "a@x.com",
        "to": "b@y.com",
        "date": "Mon, 1 Jan 2024 00:00:00 +0000",
        "body_text": "Plain body here",
    }
    assert "labelIds" not in slim
    assert "snippet" not in slim


def test_slim_gmail_dict_passes_through_non_string_header_values():
    """Non-string, non-None header values are preserved verbatim (pre-existing fallback branch)."""
    d = {
        "id": "m1",
        "threadId": "t1",
        "from": {"email": "a@b.com", "name": "A B"},
        "body_text": "Hello",
    }
    slim = slim_gmail_dict_for_llm_prompt(d)
    assert slim["from"] == {"email": "a@b.com", "name": "A B"}


def test_slim_gmail_dict_uses_snippet_when_no_body():
    d = {"id": "m1", "threadId": "t1", "snippet": "preview only"}
    slim = slim_gmail_dict_for_llm_prompt(d)
    assert slim["snippet"] == "preview only"
    assert "body_text" not in slim


def test_format_gmail_message_dict_for_llm_prompt_is_valid_json():
    d = {"id": "m1", "threadId": "t1", "from": "a@b.com", "body_text": "Hi"}
    s = format_gmail_message_dict_for_llm_prompt(d)
    parsed = json.loads(s)
    assert parsed["body_text"] == "Hi"
    assert "labelIds" not in parsed


def test_strip_invisible_email_text_returns_falsy_input_unchanged():
    """Guard branch: empty / None / 0 short-circuits and is returned as-is."""
    assert strip_invisible_email_text_for_llm("") == ""
    assert strip_invisible_email_text_for_llm(None) is None  # type: ignore[arg-type]


def test_strip_invisible_email_text_removes_cgj_and_zwsp():
    noisy = "a\u034f\u034f\u200bb\u200cc"
    assert strip_invisible_email_text_for_llm(noisy) == "abc"
    assert strip_invisible_email_text_for_llm("normal") == "normal"


def test_strip_invisible_preserves_letters_with_combining_marks():
    # Devanagari ka + nukta (legitimate combining) — not U+034F
    s = "\u0915\u093c"
    assert strip_invisible_email_text_for_llm(s) == s


def test_slim_gmail_dict_strips_invisible_from_body_and_headers():
    cgj = "\u034f"
    d = {
        "id": "m1",
        "threadId": "t1",
        "subject": f"Hi{cgj}",
        "from": "a@b.com",
        "body_text": f"Hello{cgj} world\u200b",
    }
    slim = slim_gmail_dict_for_llm_prompt(d)
    assert slim["subject"] == "Hi"
    assert slim["body_text"] == "Hello world"


def test_slim_gmail_dict_collapses_runaway_whitespace_in_body():
    """LLM-prompt slimmer delegates to the shared filter and collapses inline whitespace runs."""
    d = {
        "id": "m1",
        "threadId": "t1",
        "from": "a@b.com",
        "body_text": "Line\t\t\twith   tabs\n\n\n\nand blank lines",
    }
    slim = slim_gmail_dict_for_llm_prompt(d)
    assert slim["body_text"] == "Line with tabs\n\nand blank lines"


def test_slim_gmail_dict_clean_slim_string_still_strips_invisibles_via_shared_filter():
    """Regression: _clean_slim_string must continue stripping invisibles after the filter
    pipeline grew tracking-URL / orphan-link / footer passes — those new passes must not
    regress the invisible-char cleanup that LLM prompts depend on."""
    d = {
        "id": "m1",
        "threadId": "t1",
        "subject": "Quarterly\u034f update\u200b ready",
        "from": "Marketing\ufeff <m@x.com>",
        "body_text": "Hello\u034f team\u200c — please review.\n\u200b",
    }
    slim = slim_gmail_dict_for_llm_prompt(d)
    for v in (slim["subject"], slim["from"], slim["body_text"]):
        for ch in ("\u034f", "\u200b", "\u200c", "\ufeff"):
            assert ch not in v
    assert slim["subject"] == "Quarterly update ready"
    assert slim["from"] == "Marketing <m@x.com>"
    assert slim["body_text"].startswith("Hello team")


def test_format_gmail_llm_json_has_no_u034f_escapes_in_content():
    d = {
        "id": "m1",
        "threadId": "t1",
        "from": "x@test.com",
        "body_text": "x" + ("\u034f" * 20) + "y",
    }
    s = format_gmail_message_dict_for_llm_prompt(d)
    assert "\u034f" not in s
    assert "\\u034f" not in s
    assert "xy" in s or '"body_text": "xy"' in s
