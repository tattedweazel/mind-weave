"""Unit tests for app.core.text_noise (no external calls)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.core import text_noise
from app.core.text_noise import (
    DEFAULT_NOISE_FILTER,
    EMAIL_BODY_NOISE_FILTER,
    EMAIL_HEADER_NOISE_FILTER,
    NoiseFilterConfig,
    filter_text_noise,
    html_to_plain_text,
)


def test_default_presets_have_expected_safe_defaults():
    for preset in (DEFAULT_NOISE_FILTER, EMAIL_BODY_NOISE_FILTER):
        assert preset.normalize_line_endings is True
        assert preset.unescape_html_entities is True
        assert preset.decode_unicode_escape_literals is True
        assert preset.strip_invisible_unicode is True
        assert preset.drop_html_style_and_script is True
        assert preset.collapse_whitespace is True
        assert preset.strip_repeated_separators is True
        assert preset.strip_tracking_url_params is True
        assert preset.shorten_long_urls is True
        assert preset.long_url_threshold == 120
        assert preset.strip_orphan_link_placeholders is True
        assert preset.strip_quoted_reply_chains is False
        assert preset.max_chars == 8000
    assert DEFAULT_NOISE_FILTER.strip_marketing_footers is False
    assert EMAIL_BODY_NOISE_FILTER.strip_marketing_footers is True


def test_email_header_noise_filter_preset_is_a_light_touch():
    preset = EMAIL_HEADER_NOISE_FILTER
    assert preset.normalize_line_endings is True
    assert preset.unescape_html_entities is True
    assert preset.decode_unicode_escape_literals is True
    assert preset.strip_invisible_unicode is True
    assert preset.collapse_whitespace is True
    assert preset.drop_html_style_and_script is False
    assert preset.strip_repeated_separators is False
    assert preset.strip_tracking_url_params is False
    assert preset.shorten_long_urls is False
    assert preset.strip_orphan_link_placeholders is False
    assert preset.strip_quoted_reply_chains is False
    assert preset.strip_marketing_footers is False
    assert preset.max_chars is None


def test_filter_text_noise_returns_empty_for_empty_or_non_string():
    assert filter_text_noise("") == ("", False)
    assert filter_text_noise(None) == ("", False)  # type: ignore[arg-type]
    assert filter_text_noise(0) == ("", False)  # type: ignore[arg-type]


def test_filter_text_noise_strips_invisible_unicode_and_cf_category():
    # Includes CGJ (range hit), ZWSP (range hit), and SOFT HYPHEN U+00AD (Cf branch only).
    text = "a\u034fb\u200bc\u00ade"
    out, truncated = filter_text_noise(text, NoiseFilterConfig(max_chars=None))
    assert out == "abce"
    assert truncated is False


def test_filter_text_noise_preserves_legitimate_combining_marks():
    # Devanagari ka + nukta — Mn category, not Cf — must survive.
    text = "\u0915\u093c"
    out, _ = filter_text_noise(text, NoiseFilterConfig(max_chars=None))
    assert out == text


def test_filter_text_noise_can_disable_invisible_strip():
    cgj = "\u034f"
    out, _ = filter_text_noise(
        f"a{cgj}b",
        NoiseFilterConfig(
            strip_invisible_unicode=False,
            collapse_whitespace=False,
            max_chars=None,
        ),
    )
    assert out == f"a{cgj}b"


def test_filter_text_noise_strips_repeated_separators():
    text = "Header\n----------\nBody\n=====\nMore\n***\nNot a sep --"
    out, _ = filter_text_noise(text, NoiseFilterConfig(max_chars=None))
    # Lines of pure dashes / equals are dropped (left blank, then whitespace collapse trims).
    assert "----------" not in out
    assert "=====" not in out
    assert "Body" in out
    assert "More" in out
    assert "Not a sep" in out  # too short / mixed content stays


def test_filter_text_noise_can_disable_separator_strip():
    out, _ = filter_text_noise(
        "----------",
        NoiseFilterConfig(
            strip_repeated_separators=False,
            collapse_whitespace=False,
            max_chars=None,
        ),
    )
    assert out == "----------"


def test_filter_text_noise_shortens_long_urls_above_threshold():
    short_url = "https://example.com/page"
    long_url = "https://tracker.example.com/click?" + ("a" * 200)
    text = f"see {short_url} or {long_url} please"
    out, _ = filter_text_noise(
        text,
        NoiseFilterConfig(long_url_threshold=80, max_chars=None),
    )
    assert short_url in out
    assert long_url not in out
    assert "[link]" in out


def test_filter_text_noise_can_disable_url_shortening():
    long_url = "https://example.com/" + ("z" * 300)
    out, _ = filter_text_noise(
        long_url,
        NoiseFilterConfig(shorten_long_urls=False, max_chars=None),
    )
    assert long_url == out


def test_filter_text_noise_strips_quoted_reply_chains_when_enabled():
    text = (
        "Hi there,\nOn Mon, 1 Jan 2024 at 09:00, Person <p@x.com> wrote:\n> previous content\n>> deeper quote\nThanks!"
    )
    out, _ = filter_text_noise(
        text,
        NoiseFilterConfig(
            strip_quoted_reply_chains=True,
            collapse_whitespace=True,
            max_chars=None,
        ),
    )
    assert "previous content" not in out
    assert "deeper quote" not in out
    assert "wrote:" not in out
    assert "Hi there" in out
    assert "Thanks!" in out


def test_filter_text_noise_strips_outlook_style_reply_header():
    text = "My reply.\n-------- Original Message --------\nFrom: someone@x.com\nOld body line"
    out, _ = filter_text_noise(
        text,
        NoiseFilterConfig(
            strip_quoted_reply_chains=True,
            strip_repeated_separators=False,
            collapse_whitespace=True,
            max_chars=None,
        ),
    )
    assert "Original Message" not in out
    assert "From:" not in out
    assert "My reply." in out


def test_filter_text_noise_strips_marketing_footers_when_enabled():
    text = (
        "Real content here.\n"
        "Click here to unsubscribe from our list.\n"
        "View this email in your browser.\n"
        "Manage your email preferences anytime.\n"
        "Follow us on Twitter.\n"
        "Privacy Policy applies.\n"
        "Copyright (c) 2026 Example Inc.\n"
        "Footer text that survives."
    )
    out, _ = filter_text_noise(
        text,
        NoiseFilterConfig(
            strip_marketing_footers=True,
            collapse_whitespace=True,
            max_chars=None,
        ),
    )
    assert "unsubscribe" not in out.lower()
    assert "browser" not in out.lower()
    assert "preferences" not in out.lower()
    assert "follow us" not in out.lower()
    assert "privacy policy" not in out.lower()
    assert "copyright" not in out.lower()
    assert "Real content here." in out
    assert "Footer text that survives." in out


def test_filter_text_noise_collapses_whitespace_runs_and_blank_lines():
    text = "a\t  b   c\n\n\n\nnext line\n   \n end "
    out, _ = filter_text_noise(text, NoiseFilterConfig(max_chars=None))
    # Inline runs of \t / space collapse to a single space; trailing space-before-newline is
    # dropped; 3+ newlines collapse to a paragraph break; outer whitespace is .strip()ped.
    # Leading whitespace on lines is preserved (could be intentional indentation).
    assert out == "a b c\n\nnext line\n\n end"


def test_filter_text_noise_can_disable_whitespace_collapse():
    text = "a   b\n\n\n\n c"
    out, _ = filter_text_noise(
        text,
        NoiseFilterConfig(collapse_whitespace=False, max_chars=None),
    )
    assert out == text


def test_filter_text_noise_truncates_to_max_chars_and_reports_truncation():
    text = "x" * 100
    out, truncated = filter_text_noise(
        text,
        NoiseFilterConfig(max_chars=20, collapse_whitespace=False),
    )
    assert out == "x" * 20
    assert truncated is True


def test_filter_text_noise_does_not_truncate_when_within_cap():
    out, truncated = filter_text_noise(
        "short",
        NoiseFilterConfig(max_chars=100),
    )
    assert out == "short"
    assert truncated is False


def test_filter_text_noise_max_chars_none_means_no_cap():
    text = "y" * 50_000
    out, truncated = filter_text_noise(
        text,
        NoiseFilterConfig(max_chars=None, collapse_whitespace=False),
    )
    assert len(out) == 50_000
    assert truncated is False


def test_filter_text_noise_is_idempotent_on_its_own_output():
    text = "Hello\u034f world\n\n\n\n------------\nVisit https://" + ("a" * 200) + " now\t   please"
    once, _ = filter_text_noise(text)
    twice, twice_trunc = filter_text_noise(once)
    assert once == twice
    assert twice_trunc is False


def test_html_to_plain_text_returns_empty_for_empty_input():
    assert html_to_plain_text("") == ""
    assert html_to_plain_text("   ") == ""


def test_html_to_plain_text_strips_tags_and_unescapes_entities():
    assert html_to_plain_text("<p>Hello &amp; <b>world</b></p>") == "Hello & world"


def test_html_to_plain_text_drops_style_and_script_content_by_default():
    html = (
        "<html><head>"
        "<style>.x { color: red; background: url(https://t.example/pixel?id=ABCDEF); }</style>"
        "<script>var x = 1; alert('hi');</script>"
        "</head><body><p>Visible only.</p></body></html>"
    )
    out = html_to_plain_text(html)
    assert "color" not in out
    assert "alert" not in out
    assert "Visible only." in out


def test_html_to_plain_text_can_keep_style_and_script_when_disabled():
    html = "<style>.a{color:red}</style><p>Body</p>"
    cfg = NoiseFilterConfig(drop_html_style_and_script=False, max_chars=None)
    out = html_to_plain_text(html, cfg)
    assert ".a{color:red}" in out
    assert "Body" in out


def test_html_to_plain_text_handles_nested_ignored_tags():
    html = "<style><style>nested</style></style><p>Kept</p>"
    out = html_to_plain_text(html)
    assert "nested" not in out
    assert "Kept" in out


def test_html_to_plain_text_falls_back_to_regex_strip_on_parser_exception(monkeypatch):
    class _Boom:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def feed(self, _data: str) -> None:
            raise RuntimeError("parser exploded")

        def close(self) -> None:  # pragma: no cover - never reached
            pass

        def text(self) -> str:  # pragma: no cover - never reached
            return ""

    monkeypatch.setattr(text_noise, "_PlainTextExtractor", _Boom)
    out = html_to_plain_text("<p>Hi <b>there</b>!</p>")
    # Regex fallback strips tags, then filter_text_noise collapses runs of whitespace.
    assert out == "Hi there !"


@pytest.mark.parametrize(
    "html, expected_substring",
    [
        ("<p>One</p><p>Two</p>", "One"),
        ("<p>One</p><p>Two</p>", "Two"),
        ("plain text", "plain text"),
    ],
)
def test_html_to_plain_text_marketing_style_fixture(html, expected_substring):
    out = html_to_plain_text(html)
    assert expected_substring in out


def test_html_to_plain_text_strips_long_tracking_url_inside_anchor_text():
    """Long anchor text replaced with `[link]` by the noise filter (orphan-line drop disabled
    here so we can assert the URL-shortening pass directly; orphan-line behaviour is covered
    in its own test and in test_curated_gmail_message_drops_orphan_link_placeholder_lines.)"""
    long_url = "https://tracker.example.com/" + ("p" * 300)
    html = f'<a href="{long_url}">{long_url}</a>'
    cfg = NoiseFilterConfig(strip_orphan_link_placeholders=False, max_chars=None)
    out = html_to_plain_text(html, cfg)
    assert long_url not in out
    assert "[link]" in out


def test_replace_preserves_other_fields_when_overriding_max_chars():
    cfg = replace(EMAIL_BODY_NOISE_FILTER, max_chars=100)
    assert cfg.max_chars == 100
    assert cfg.shorten_long_urls is True
    assert cfg.drop_html_style_and_script is True


# --- v2 knobs --------------------------------------------------------------------------


def test_normalize_line_endings_maps_crlf_and_lone_cr_to_lf():
    cfg = NoiseFilterConfig(collapse_whitespace=False, max_chars=None)
    out, _ = filter_text_noise("a\r\nb\rc\n\r\n\r\nd", cfg)
    assert "\r" not in out
    assert out == "a\nb\nc\n\n\nd"


def test_normalize_line_endings_can_be_disabled():
    cfg = NoiseFilterConfig(
        normalize_line_endings=False,
        collapse_whitespace=False,
        max_chars=None,
    )
    out, _ = filter_text_noise("a\r\nb", cfg)
    assert out == "a\r\nb"


def test_normalize_line_endings_lets_subsequent_passes_collapse_blank_paragraphs():
    cfg = NoiseFilterConfig(max_chars=None)
    out, _ = filter_text_noise("a\r\n\r\n\r\n\r\nb", cfg)
    assert out == "a\n\nb"


def test_unescape_html_entities_decodes_named_and_numeric_forms():
    cfg = NoiseFilterConfig(
        strip_invisible_unicode=False,
        collapse_whitespace=False,
        max_chars=None,
    )
    out, _ = filter_text_noise("a&zwnj;b&nbsp;c&#x200B;d&amp;e", cfg)
    # &zwnj; → U+200C (Cf, but we disabled strip_invisible_unicode in this test)
    assert "\u200c" in out
    assert "\xa0" in out  # &nbsp;
    assert "\u200b" in out  # &#x200B;
    assert "&amp;" not in out
    assert "&" in out  # &amp; → &; must NOT be re-stripped


def test_unescape_then_strip_invisible_unicode_collapses_zwnj_blob():
    text = "Hello&zwnj;&zwnj;&zwnj;world"
    out, _ = filter_text_noise(text, NoiseFilterConfig(max_chars=None))
    # &zwnj; decodes to U+200C (zero-width non-joiner, category Cf) → stripped.
    assert out == "Helloworld"


def test_unescape_html_entities_can_be_disabled():
    cfg = NoiseFilterConfig(
        unescape_html_entities=False,
        strip_invisible_unicode=False,
        collapse_whitespace=False,
        max_chars=None,
    )
    out, _ = filter_text_noise("a&amp;b", cfg)
    assert out == "a&amp;b"


def test_filter_text_noise_decodes_plaintext_unicode_slash_u_escapes():
    # As in scraped/JSON-ish text, not as HTML entities.
    one = "Price: " + "\\" + "u" + "00a3" + " 5"
    two = 2 * "\\" + "u" + "00a3"  # over-escaped leading backslashes
    out1, _ = filter_text_noise(one, NoiseFilterConfig(max_chars=None))
    out2, _ = filter_text_noise(two, NoiseFilterConfig(max_chars=None))
    assert "£" in out1
    assert out1 == "Price: £ 5"
    assert out2 == "£"
    assert "\\" not in out1
    assert "u00a3" not in out1


def test_filter_text_noise_decodes_slash_Upper_u_eight_hex():
    s = "\\" + "U" + "000000A3"
    out, _ = filter_text_noise("x " + s, NoiseFilterConfig(max_chars=None))
    assert "£" in out
    assert out == "x £"


def test_filter_text_noise_leaves_out_of_range_slash_U_escape_unchanged():
    bad = "\\" + "U" + "00110000"  # > U+10FFFF; must not break the string
    out, _ = filter_text_noise("a" + bad + "b", NoiseFilterConfig(max_chars=None))
    assert bad in out


def test_filter_text_noise_can_disable_unicode_escape_literal_decode():
    raw = "x" + "\\" + "u" + "00a3" + "y"
    cfg = NoiseFilterConfig(
        decode_unicode_escape_literals=False,
        strip_invisible_unicode=False,
        collapse_whitespace=False,
        max_chars=None,
    )
    out, _ = filter_text_noise(raw, cfg)
    assert "£" not in out
    assert "u" in out


def test_strip_tracking_url_params_drops_known_keys():
    cfg = NoiseFilterConfig(
        shorten_long_urls=False,
        collapse_whitespace=False,
        max_chars=None,
    )
    text = (
        "see https://example.com/page?utm_source=foo&utm_medium=email"
        "&mc_cid=400fae032d&mc_eid=UNIQID&id=42&q=hello#anchor here"
    )
    out, _ = filter_text_noise(text, cfg)
    assert "utm_source" not in out
    assert "utm_medium" not in out
    assert "mc_cid" not in out
    assert "mc_eid" not in out
    assert "id=42" in out
    assert "q=hello" in out
    assert "#anchor" in out


def test_strip_tracking_url_params_preserves_clean_urls_unchanged():
    cfg = NoiseFilterConfig(
        shorten_long_urls=False,
        collapse_whitespace=False,
        max_chars=None,
    )
    url = "https://example.com/page?id=42&q=hello"
    out, _ = filter_text_noise(f"see {url} please", cfg)
    assert url in out


def test_strip_tracking_url_params_strips_trailing_sentence_punctuation_safely():
    cfg = NoiseFilterConfig(
        shorten_long_urls=False,
        collapse_whitespace=False,
        max_chars=None,
    )
    text = "Visit https://example.com/page?utm_source=foo, then go home."
    out, _ = filter_text_noise(text, cfg)
    assert "utm_source" not in out
    assert "https://example.com/page" in out
    assert ", then go home." in out  # trailing comma preserved as sentence punctuation


def test_strip_tracking_url_params_is_idempotent_on_already_clean_url():
    cfg = NoiseFilterConfig(
        shorten_long_urls=False,
        collapse_whitespace=False,
        max_chars=None,
    )
    url = "https://example.com/p?id=1"
    once, _ = filter_text_noise(url, cfg)
    twice, _ = filter_text_noise(once, cfg)
    assert once == url
    assert twice == once


def test_strip_tracking_url_params_safe_on_url_without_query():
    cfg = NoiseFilterConfig(
        shorten_long_urls=False,
        collapse_whitespace=False,
        max_chars=None,
    )
    url = "https://example.com/page#section"
    out, _ = filter_text_noise(url, cfg)
    assert out == url


def test_strip_tracking_url_params_lets_short_mailchimp_urls_survive_length_check():
    # Email #2 sample shape: ~110-char mailchimp URL; below the 120-char threshold only
    # AFTER tracking params are stripped first.
    cfg = NoiseFilterConfig(max_chars=None)
    url = (
        "https://example.us12.list-manage.com/track/click?"
        "u=abcdef0123456789&id=400fae032d&e=UNIQID&mc_cid=400fae032d&mc_eid=UNIQID"
    )
    out, _ = filter_text_noise(url, cfg)
    assert "[link]" not in out
    assert "mc_cid" not in out
    assert "mc_eid" not in out
    assert "u=abcdef0123456789" in out
    assert "id=400fae032d" in out


def test_strip_tracking_url_params_can_be_disabled():
    cfg = NoiseFilterConfig(
        strip_tracking_url_params=False,
        shorten_long_urls=False,
        collapse_whitespace=False,
        max_chars=None,
    )
    url = "https://example.com/p?utm_source=x&id=1"
    out, _ = filter_text_noise(url, cfg)
    assert out == url


def test_strip_tracking_url_params_is_safe_on_malformed_url(monkeypatch):
    cfg = NoiseFilterConfig(
        shorten_long_urls=False,
        collapse_whitespace=False,
        max_chars=None,
    )

    def boom(_url: str, *_args: object, **_kwargs: object) -> object:
        raise ValueError("malformed URL")

    monkeypatch.setattr(text_noise, "urlsplit", boom)
    text = "see https://example.com/page?utm_source=x for details"
    out, _ = filter_text_noise(text, cfg)
    # urlsplit raised → URL passes through untouched (caller never sees an exception).
    assert "https://example.com/page?utm_source=x" in out


def test_strip_orphan_link_placeholders_drops_lines():
    cfg = NoiseFilterConfig(
        collapse_whitespace=True,
        max_chars=None,
    )
    text = "Real first line.\n[link]\n( [link] )\n- [link]\n• [link] •\nClick [link] for details.\nReal last line."
    out, _ = filter_text_noise(text, cfg)
    assert "Real first line." in out
    assert "Real last line." in out
    assert "Click [link] for details." in out
    # Standalone placeholders gone.
    assert "( [link] )" not in out
    assert "- [link]" not in out
    assert "• [link] •" not in out


def test_strip_orphan_link_placeholders_can_be_disabled():
    cfg = NoiseFilterConfig(
        strip_orphan_link_placeholders=False,
        collapse_whitespace=False,
        max_chars=None,
    )
    text = "[link]\n( [link] )"
    out, _ = filter_text_noise(text, cfg)
    assert out == text


def test_email_body_filter_default_strips_marketing_footers():
    text = "Real content here.\nClick here to unsubscribe.\nFooter text that survives."
    out, _ = filter_text_noise(text, EMAIL_BODY_NOISE_FILTER)
    assert "unsubscribe" not in out.lower()
    assert "Real content here." in out
    assert "Footer text that survives." in out


def test_email_header_filter_cleans_invisibles_but_does_not_drop_footer_words():
    raw = "Click \u200bhere to unsubscribe \u034ffrom our list\xa0please"
    out, _ = filter_text_noise(raw, EMAIL_HEADER_NOISE_FILTER)
    # No invisible/format chars, but the marketing-footer pattern was NOT applied (header preset).
    assert "unsubscribe" in out.lower()
    assert "\u200b" not in out
    assert "\u034f" not in out


def test_filter_pipeline_combined_noise_is_idempotent():
    text = (
        "Subject blob\u034f \u200b&zwnj;&zwnj;&zwnj;&nbsp;more\r\n"
        "----------\r\n"
        "Visit https://t.example.com/click?utm_source=x&utm_medium=email&id=42 now\r\n"
        "( [link] )\r\n"
        "Click here to unsubscribe.\r\n"
        "Real body line.\r\n"
        "https://very.example/" + ("a" * 300) + "\r\n"
    )
    once, _ = filter_text_noise(text, EMAIL_BODY_NOISE_FILTER)
    twice, twice_trunc = filter_text_noise(once, EMAIL_BODY_NOISE_FILTER)
    assert once == twice
    assert twice_trunc is False
    # Spot-check the cleaning happened.
    assert "\r" not in once
    assert "&zwnj;" not in once
    assert "----------" not in once
    assert "utm_source" not in once
    # The very-long URL was shortened to `[link]` then dropped as an orphan-link line.
    assert "very.example" not in once
    assert "( [link] )" not in once
    assert "unsubscribe" not in once.lower()
    assert "Real body line." in once
