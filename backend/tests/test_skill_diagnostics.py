"""Unit tests for workflow skill diagnostics helpers."""

import base64

from app.domain.workflow_executor.diagnostics import (
    GMAIL_MESSAGE_BODY_MAX_CHARS,
    GMAIL_MESSAGES_LIST_MAX_FOR_DIAGNOSTICS,
    GOOGLE_CALENDAR_LIST_EVENTS_MAX_ITEMS_FOR_DIAGNOSTICS,
    SKILL_DIAGNOSTICS_KEY,
    curated_gmail_message_from_full_api,
    curated_gmail_messages_list_item,
    curated_google_calendar_event,
    html_to_plain_text,
    merge_skill_diagnostics,
    truncate_gmail_messages_list_response,
    truncate_google_calendar_events_list_response,
)


def test_merge_skill_diagnostics():
    d = merge_skill_diagnostics(
        {"event_count": 1},
        vendor_key="google_calendar_v3",
        payload={"operation": "events.list", "response": {}},
    )
    assert d["event_count"] == 1
    assert SKILL_DIAGNOSTICS_KEY in d
    assert d[SKILL_DIAGNOSTICS_KEY]["google_calendar_v3"]["operation"] == "events.list"


def test_merge_skill_diagnostics_preserves_existing_vendor():
    d0 = merge_skill_diagnostics(
        {},
        vendor_key="gmail_v1",
        payload={"operation": "list"},
    )
    d1 = merge_skill_diagnostics(
        d0,
        vendor_key="google_calendar_v3",
        payload={"operation": "events.list"},
    )
    assert set(d1[SKILL_DIAGNOSTICS_KEY].keys()) == {"gmail_v1", "google_calendar_v3"}


def test_truncate_google_calendar_events_list_response():
    raw = {"items": [{"id": f"e{i}"} for i in range(150)], "nextPageToken": "x"}
    out, truncated, omitted = truncate_google_calendar_events_list_response(
        raw,
        max_items=GOOGLE_CALENDAR_LIST_EVENTS_MAX_ITEMS_FOR_DIAGNOSTICS,
    )
    assert truncated
    assert omitted == 150 - GOOGLE_CALENDAR_LIST_EVENTS_MAX_ITEMS_FOR_DIAGNOSTICS
    assert len(out["items"]) == GOOGLE_CALENDAR_LIST_EVENTS_MAX_ITEMS_FOR_DIAGNOSTICS
    assert out["nextPageToken"] == "x"


def test_truncate_gmail_messages_list_response():
    raw = {"messages": [{"id": f"m{i}"} for i in range(150)], "resultSizeEstimate": 999}
    out, truncated, omitted = truncate_gmail_messages_list_response(
        raw,
        max_messages=GMAIL_MESSAGES_LIST_MAX_FOR_DIAGNOSTICS,
    )
    assert truncated
    assert omitted == 150 - GMAIL_MESSAGES_LIST_MAX_FOR_DIAGNOSTICS
    assert len(out["messages"]) == GMAIL_MESSAGES_LIST_MAX_FOR_DIAGNOSTICS


def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_curated_gmail_message_from_full_simple():
    msg = {
        "id": "m1",
        "threadId": "th1",
        "snippet": "snip",
        "labelIds": ["INBOX"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": "Subj"},
                {"name": "From", "value": "me@x.com"},
                {"name": "Date", "value": "Mon, 1 Jan 2024 00:00:00 +0000"},
            ],
            "body": {"data": _b64url("Hello body")},
        },
    }
    c = curated_gmail_message_from_full_api(msg, max_body_chars=GMAIL_MESSAGE_BODY_MAX_CHARS)
    assert c["id"] == "m1"
    assert c["threadId"] == "th1"
    assert c["subject"] == "Subj"
    assert c["from"] == "me@x.com"
    assert c["body_text"] == "Hello body"
    assert c["snippet"] == "snip"
    assert c["labelIds"] == ["INBOX"]
    assert "body_truncated" not in c


def test_curated_gmail_message_multipart_prefers_plain():
    msg = {
        "id": "x",
        "threadId": "y",
        "payload": {
            "mimeType": "multipart/alternative",
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": _b64url("plain here")},
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": _b64url("<p>html</p>")},
                },
            ],
        },
    }
    c = curated_gmail_message_from_full_api(msg)
    assert c["body_text"] == "plain here"
    assert "body_html" not in c


def test_html_to_plain_text_strips_tags():
    assert html_to_plain_text("<p>Hello &amp; <b>world</b></p>") == "Hello & world"


def test_curated_gmail_message_html_only_strips_to_text():
    msg = {
        "id": "h1",
        "threadId": "t1",
        "payload": {
            "mimeType": "text/html",
            "headers": [],
            "body": {"data": _b64url("<div><p>Hi there</p></div>")},
        },
    }
    c = curated_gmail_message_from_full_api(msg)
    assert c["body_text"] == "Hi there"
    assert "body_html" not in c


def test_curated_gmail_message_truncates_body():
    big = "x" * 50
    msg = {
        "id": "x",
        "payload": {
            "mimeType": "text/plain",
            "headers": [],
            "body": {"data": _b64url(big)},
        },
    }
    c = curated_gmail_message_from_full_api(msg, max_body_chars=20)
    assert len(c["body_text"]) == 20
    assert c["body_truncated"] is True


def test_curated_gmail_message_html_drops_style_and_script_blocks():
    """HTML bodies must not leak <style>/<script> text into body_text — primary source of bloat."""
    html = (
        "<html><head>"
        "<style>.btn { color:#fff; background:url(https://t.example/pixel?id=ABC); }</style>"
        "<script>console.log('tracker')</script>"
        "</head><body><p>The actual message.</p></body></html>"
    )
    msg = {
        "id": "h1",
        "threadId": "t1",
        "payload": {
            "mimeType": "text/html",
            "headers": [],
            "body": {"data": _b64url(html)},
        },
    }
    c = curated_gmail_message_from_full_api(msg)
    assert "color" not in c["body_text"]
    assert "console.log" not in c["body_text"]
    assert "The actual message." in c["body_text"]
    assert "body_truncated" not in c


def test_curated_gmail_message_shortens_long_tracking_url_in_body():
    """Long tracking URLs in plain bodies are replaced with [link] by the noise filter."""
    long_url = "https://tracker.example.com/click?" + ("p" * 250)
    body = f"Hello,\nClick {long_url} to confirm.\nThanks!"
    msg = {
        "id": "u1",
        "threadId": "t1",
        "payload": {
            "mimeType": "text/plain",
            "headers": [],
            "body": {"data": _b64url(body)},
        },
    }
    c = curated_gmail_message_from_full_api(msg)
    assert long_url not in c["body_text"]
    assert "[link]" in c["body_text"]
    assert "Hello," in c["body_text"]


def test_curated_gmail_message_default_cap_matches_email_preset():
    """Default GMAIL_MESSAGE_BODY_MAX_CHARS is sourced from EMAIL_BODY_NOISE_FILTER (8,000)."""
    from app.core.text_noise import EMAIL_BODY_NOISE_FILTER

    assert GMAIL_MESSAGE_BODY_MAX_CHARS == EMAIL_BODY_NOISE_FILTER.max_chars
    assert GMAIL_MESSAGE_BODY_MAX_CHARS == 8000


def test_curated_gmail_messages_list_item():
    ref = {"id": "abc", "threadId": "t1", "internalDate": "1234567890"}
    c = curated_gmail_messages_list_item(ref)
    assert c == {"id": "abc", "threadId": "t1", "internalDate": "1234567890"}
    assert curated_gmail_messages_list_item({"id": "x", "threadId": "y", "foo": "bar"}) == {
        "id": "x",
        "threadId": "y",
    }


def test_curated_gmail_message_snippet_strips_invisible_unicode():
    """Snippet field carried U+034F / ZWSP / ZWNJ padding straight through to consumers."""
    snip = "\u034f \u200c \ufeff \u034f \u200c"  # invisibles + spaces only
    msg = {
        "id": "s1",
        "threadId": "t1",
        "snippet": "Hi\u034f there\u200b friend",
        "payload": {"headers": []},
    }
    c = curated_gmail_message_from_full_api(msg)
    assert "\u034f" not in c["snippet"]
    assert "\u200b" not in c["snippet"]
    assert c["snippet"] == "Hi there friend"

    msg2 = {**msg, "id": "s2", "snippet": snip}
    c2 = curated_gmail_message_from_full_api(msg2)
    # All invisibles removed, only whitespace remained, then collapse + strip → "" → field omitted.
    assert "snippet" not in c2


def test_curated_gmail_message_subject_strips_invisible_unicode_and_entities():
    msg = {
        "id": "h2",
        "threadId": "t1",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Re:\u034f\u200b Newsletter &amp; updates"},
                {"name": "From", "value": "Marketing\u034f <m@x.com>"},
            ],
        },
    }
    c = curated_gmail_message_from_full_api(msg)
    assert c["subject"] == "Re: Newsletter & updates"
    assert "\u034f" not in c["from"]
    assert c["from"] == "Marketing <m@x.com>"


def test_curated_gmail_message_plain_zwnj_blob_collapses_to_negligible():
    """Real-world: plain-text MIME parts with ~100x literal &zwnj; entities."""
    body = "Hello\n" + ("&zwnj; " * 100) + "\nThe rest of the message."
    msg = {
        "id": "z1",
        "payload": {
            "mimeType": "text/plain",
            "headers": [],
            "body": {"data": _b64url(body)},
        },
    }
    c = curated_gmail_message_from_full_api(msg)
    # &zwnj; → U+200C → stripped. The 100x blob collapses to whitespace, which the whitespace
    # collapse pass reduces to a single blank line between the two real lines.
    assert "&zwnj;" not in c["body_text"]
    assert "\u200c" not in c["body_text"]
    assert "Hello" in c["body_text"]
    assert "The rest of the message." in c["body_text"]
    # Total body length must be a small multiple of the real content.
    assert len(c["body_text"]) < 100


def test_curated_gmail_message_strips_mailchimp_tracking_params_from_body_urls():
    """Mailchimp links keep their identity but lose mc_cid / mc_eid noise (per allow-list)."""
    url_raw = (
        "https://example.us12.list-manage.com/track/click?"
        "u=abcdef0123456789&id=400fae032d&e=UNIQID&mc_cid=400fae032d&mc_eid=UNIQID"
    )
    body = f"See {url_raw} for details."
    msg = {
        "id": "mc1",
        "payload": {
            "mimeType": "text/plain",
            "headers": [],
            "body": {"data": _b64url(body)},
        },
    }
    c = curated_gmail_message_from_full_api(msg)
    assert "mc_cid" not in c["body_text"]
    assert "mc_eid" not in c["body_text"]
    assert "u=abcdef0123456789" in c["body_text"]
    assert "id=400fae032d" in c["body_text"]
    # URL stayed intact (not replaced with [link]) — survives the long-URL threshold after cleanup.
    assert "[link]" not in c["body_text"]


def test_curated_gmail_message_drops_orphan_link_placeholder_lines_from_html_body():
    """HTML bodies whose anchors became `[link]` after long-URL shortening lose orphan-only lines."""
    long_href = "https://tracker.example.com/click?" + ("z" * 300)
    html = (
        f'<p>Real intro paragraph.</p>'
        f'<p>(<a href="{long_href}">{long_href}</a>)</p>'
        f'<p>Closing line.</p>'
    )
    msg = {
        "id": "lk1",
        "payload": {
            "mimeType": "text/html",
            "headers": [],
            "body": {"data": _b64url(html)},
        },
    }
    c = curated_gmail_message_from_full_api(msg)
    assert "Real intro paragraph." in c["body_text"]
    assert "Closing line." in c["body_text"]
    # The middle paragraph collapsed to "( [link] )" then was dropped as an orphan-link line.
    assert "( [link] )" not in c["body_text"]


def test_curated_gmail_message_drops_marketing_footer_lines_by_default():
    """EMAIL_BODY_NOISE_FILTER now ships with strip_marketing_footers=True for Gmail bodies."""
    body = (
        "Hello!\n"
        "This is the real body of the email.\n"
        "Click here to unsubscribe at any time.\n"
        "View this email in your browser.\n"
        "Privacy Policy applies.\n"
        "Goodbye."
    )
    msg = {
        "id": "f1",
        "payload": {
            "mimeType": "text/plain",
            "headers": [],
            "body": {"data": _b64url(body)},
        },
    }
    c = curated_gmail_message_from_full_api(msg)
    assert "unsubscribe" not in c["body_text"].lower()
    assert "browser" not in c["body_text"].lower()
    assert "privacy policy" not in c["body_text"].lower()
    assert "Hello!" in c["body_text"]
    assert "real body" in c["body_text"]
    assert "Goodbye." in c["body_text"]


def test_curated_google_calendar_event_all_day():
    ev = {
        "id": "x",
        "status": "confirmed",
        "summary": "Trip",
        "start": {"date": "2026-03-23"},
        "end": {"date": "2026-03-24"},
    }
    c = curated_google_calendar_event(ev)
    assert c["id"] == "x"
    assert c["start"] == "2026-03-23"
    assert c["end"] == "2026-03-24"
    assert c["summary"] == "Trip"
