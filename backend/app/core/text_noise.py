"""
Reusable text-noise filter for HTML-derived bodies (e.g. marketing email) before they reach
LLMs, run logs, or downstream graph nodes.

Single source of truth for "scrub a noisy body of text". Wire integrations through
``filter_text_noise()`` (or ``html_to_plain_text()`` for HTML inputs) and tune behaviour by
passing a ``NoiseFilterConfig`` rather than copy-pasting regexes.

Stdlib-only. Pure and deterministic. ``filter_text_noise`` is idempotent on its own output
when run with the same config (running it twice yields the same string).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class NoiseFilterConfig:
    """
    Configuration knobs for ``filter_text_noise`` / ``html_to_plain_text``.

    Defaults remove obvious machine-generated noise (line-ending normalization, HTML entity
    decoding, invisible characters, ``<style>`` / ``<script>`` text, repeated layout
    separators, tracking query params, very long URLs, ``[link]`` orphan lines, runaway
    whitespace) without dropping content the user likely wants. Quoted reply chains and
    marketing-footer detection are opt-in here because they can have false positives in
    legitimate prose; the ``EMAIL_BODY_NOISE_FILTER`` preset enables the footer pass for
    Gmail bodies where the false-positive cost is low.
    When ``decode_unicode_escape_literals`` is True, plain-text ``\\uFFFF`` / ``\\U…`` runs
    (including over-escaped ``\\\\u…`` from scrapes) become real characters after HTML entities.
    """

    normalize_line_endings: bool = True
    unescape_html_entities: bool = True
    decode_unicode_escape_literals: bool = True
    strip_invisible_unicode: bool = True
    drop_html_style_and_script: bool = True
    strip_repeated_separators: bool = True
    strip_tracking_url_params: bool = True
    shorten_long_urls: bool = True
    long_url_threshold: int = 120
    strip_orphan_link_placeholders: bool = True
    strip_quoted_reply_chains: bool = False
    strip_marketing_footers: bool = False
    collapse_whitespace: bool = True
    max_chars: Optional[int] = 8000


DEFAULT_NOISE_FILTER = NoiseFilterConfig()
"""Generic default applied across the codebase when no caller-specific tuning is needed."""

EMAIL_BODY_NOISE_FILTER = NoiseFilterConfig(
    strip_marketing_footers=True,
)
"""Preset used for Gmail message ``body_text`` extraction (see ``diagnostics.py``)."""

EMAIL_HEADER_NOISE_FILTER = NoiseFilterConfig(
    drop_html_style_and_script=False,
    strip_repeated_separators=False,
    strip_tracking_url_params=False,
    shorten_long_urls=False,
    strip_orphan_link_placeholders=False,
    strip_quoted_reply_chains=False,
    strip_marketing_footers=False,
    max_chars=None,
)
"""
Preset for short string fields like ``subject`` / ``snippet`` / ``from`` / ``to`` / ``date``.

Only invisible-Unicode + HTML-entity cleanup + whitespace collapse — no truncation, no URL
rewriting, no footer stripping. Used by the curated Gmail step so subjects and snippets stop
carrying the same invisible-character spam that we already remove from bodies.
"""


_INVISIBLE_RANGES: tuple[tuple[int, int], ...] = (
    (0x034F, 0x034F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x2064),
    (0xFEFF, 0xFEFF),
)

_REPEATED_SEPARATOR_RE = re.compile(r"^\s*[-=*_~]{4,}\s*$")
# Match URLs but stop at whitespace AND common closing punctuation (`)`, `]`, `}`, `>`, `<`,
# `"`, `'`, `|`) so adjacent text inside flat HTML extracts (no whitespace between sibling
# blocks) doesn't get slurped into the URL match.
_URL_RE = re.compile(r"https?://[^\s)\]}>'\"<|]+", re.IGNORECASE)
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_INLINE_WS_RE = re.compile(r"[ \t\f\v]+")
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")
_QUOTED_REPLY_HEADER_RE = re.compile(
    r"^\s*(?:on\s.+wrote:|-{2,}\s*original message\s*-{2,}|from:\s.+)\s*$",
    re.IGNORECASE,
)
_MARKETING_FOOTER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bunsubscribe\b", re.IGNORECASE),
    re.compile(r"\bview\s+(?:this\s+email\s+)?in\s+(?:your\s+)?browser\b", re.IGNORECASE),
    re.compile(r"\bmanage\s+(?:your\s+)?(?:email\s+)?preferences\b", re.IGNORECASE),
    re.compile(r"\bfollow\s+us\s+on\b", re.IGNORECASE),
    re.compile(r"\bprivacy\s+policy\b", re.IGNORECASE),
    re.compile(r"\bcopyright\b\s*[©(c)]+", re.IGNORECASE),
)
# Lines that are nothing but a "[link]" placeholder (optionally wrapped in punctuation /
# bullet chars / whitespace). Trailing punctuation includes . , ; ! ? ) ] } > | as well as
# common bullet glyphs and dash variants used in email footers.
_ORPHAN_LINK_LINE_RE = re.compile(
    r"^[\s\[\(\{<\-\u2013\u2014\u2022\u00b7:|]*\[link\][\s\.\,;\!\?\)\]\}>\|\u2013\u2014\u2022\u00b7]*$",
    re.IGNORECASE,
)
_LINE_ENDINGS_RE = re.compile(r"\r\n?")
# One or more literal backslashes then ``u``/``U`` and hex, as in scraped JSON / JS
_RE_PLAIN_SLASH_U_4 = re.compile(r"(?:\\)+u([0-9a-fA-F]{4})")
_RE_PLAIN_SLASH_U_8 = re.compile(r"(?:\\)+U([0-9a-fA-F]{8})")
# Tracking query params we strip BEFORE the long-URL length check. Conservative allow-list:
# only well-known marketing/analytics keys that have no functional effect on the destination.
_TRACKING_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "utm_name",
        "utm_brand",
        "utm_social",
        "utm_creative_format",
        "utm_marketing_tactic",
        "mc_cid",
        "mc_eid",
        "fbclid",
        "gclid",
        "gbraid",
        "wbraid",
        "msclkid",
        "yclid",
        "dclid",
        "twclid",
        "_hsenc",
        "_hsmi",
        "hsctatracking",
        "hsa_acc",
        "hsa_cam",
        "hsa_grp",
        "hsa_ad",
        "hsa_src",
        "hsa_tgt",
        "hsa_kw",
        "hsa_mt",
        "hsa_net",
        "hsa_ver",
        "ref",
        "ref_src",
        "ref_url",
        "aff",
        "aff_id",
        "affid",
        "cid",
        "eid",
        "vero_id",
        "vero_conv",
        "mkt_tok",
        "trk",
        "trkcampaign",
        "src",
    }
)


def _normalize_line_endings(text: str) -> str:
    """Map Windows / classic-Mac line endings to ``\\n`` so the rest of the pipeline sees one form."""
    return _LINE_ENDINGS_RE.sub("\n", text)


def _unescape_html_entities(text: str) -> str:
    """
    Decode HTML entities (e.g. ``&zwnj;``, ``&nbsp;``, ``&#x200B;``, ``&amp;``) so subsequent
    passes can treat their unicode form (zero-width chars become real invisibles, etc.).
    """
    return unescape(text)


def _decode_plaintext_unicode_escape_literals(text: str) -> str:
    """
    Replace literal ``\u00a3`` / ``\\u00a3``-style (and ``\\U000000A3``) substrings with the
    corresponding character. Scrape/minify pipelines often leave these as *text* rather than
    as HTML ``&#…;`` entities.
    """

    def repl(m: re.Match[str]) -> str:
        n = int(m.group(1), 16)
        if n > 0x10FFFF:
            return m.group(0)
        return chr(n)

    out = _RE_PLAIN_SLASH_U_8.sub(repl, text)
    return _RE_PLAIN_SLASH_U_4.sub(repl, out)


def _strip_invisible_unicode(text: str) -> str:
    """Drop format / bidi / zero-width characters without touching legitimate combining marks."""
    out: list[str] = []
    for ch in text:
        o = ord(ch)
        if any(low <= o <= high for low, high in _INVISIBLE_RANGES):
            continue
        if unicodedata.category(ch) == "Cf":
            continue
        out.append(ch)
    return "".join(out)


def _strip_repeated_separators(text: str) -> str:
    """Drop lines that are nothing but a row of dashes / equals / asterisks / underscores / tildes."""
    return "\n".join("" if _REPEATED_SEPARATOR_RE.match(line) else line for line in text.split("\n"))


def _strip_tracking_url_params(text: str) -> str:
    """
    Remove well-known marketing/analytics query keys from URLs before the length check, so a
    URL whose only bulk was tracking params survives intact below ``long_url_threshold``.
    """

    def repl(match: re.Match[str]) -> str:
        url = match.group(0)
        # Trim a trailing ``)`` / ``]`` / ``,`` / ``.`` so we don't eat real sentence punctuation.
        trailing = ""
        while url and url[-1] in ").,;!?]>":
            trailing = url[-1] + trailing
            url = url[:-1]
        try:
            split = urlsplit(url)
        except ValueError:
            return match.group(0)
        if not split.query:
            return url + trailing
        kept = [
            (k, v) for k, v in parse_qsl(split.query, keep_blank_values=True) if k.lower() not in _TRACKING_QUERY_KEYS
        ]
        if len(kept) == len(parse_qsl(split.query, keep_blank_values=True)):
            return url + trailing
        new_query = urlencode(kept, doseq=True)
        cleaned = urlunsplit((split.scheme, split.netloc, split.path, new_query, split.fragment))
        return cleaned + trailing

    return _URL_RE.sub(repl, text)


def _shorten_long_urls(text: str, threshold: int) -> str:
    """Replace URLs longer than ``threshold`` characters with a short ``[link]`` placeholder."""

    def repl(match: re.Match[str]) -> str:
        url = match.group(0)
        return "[link]" if len(url) > threshold else url

    return _URL_RE.sub(repl, text)


def _strip_orphan_link_placeholders(text: str) -> str:
    """Drop lines whose entire payload is a ``[link]`` placeholder + surrounding punctuation/whitespace."""
    return "\n".join("" if _ORPHAN_LINK_LINE_RE.match(line) else line for line in text.split("\n"))


def _strip_quoted_reply_chains(text: str) -> str:
    """Drop lines starting with ``>`` and common reply-header introducers."""
    kept: list[str] = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith(">"):
            continue
        if _QUOTED_REPLY_HEADER_RE.match(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def _strip_marketing_footers(text: str) -> str:
    """Drop lines that match common transactional / marketing footer phrases."""
    kept: list[str] = []
    for line in text.split("\n"):
        if any(pat.search(line) for pat in _MARKETING_FOOTER_PATTERNS):
            continue
        kept.append(line)
    return "\n".join(kept)


def _collapse_whitespace(text: str) -> str:
    """Collapse runs of inline whitespace and limit consecutive newlines to two."""
    text = _INLINE_WS_RE.sub(" ", text)
    text = _TRAILING_WS_RE.sub("\n", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def filter_text_noise(
    text: str,
    config: NoiseFilterConfig = DEFAULT_NOISE_FILTER,
) -> tuple[str, bool]:
    """
    Apply the configured noise-reduction passes and return ``(filtered_text, was_truncated)``.

    Returns ``("", False)`` when the input is empty or non-string-like (caller doesn't have to
    pre-check). ``was_truncated`` is True only when ``config.max_chars`` was hit; pure cleanup
    never reports truncation.
    """
    if not text or not isinstance(text, str):
        return "", False

    out = text
    if config.normalize_line_endings:
        out = _normalize_line_endings(out)
    if config.unescape_html_entities:
        out = _unescape_html_entities(out)
    if config.decode_unicode_escape_literals:
        out = _decode_plaintext_unicode_escape_literals(out)
    if config.strip_invisible_unicode:
        out = _strip_invisible_unicode(out)
    if config.strip_repeated_separators:
        out = _strip_repeated_separators(out)
    if config.strip_tracking_url_params:
        out = _strip_tracking_url_params(out)
    if config.shorten_long_urls:
        out = _shorten_long_urls(out, config.long_url_threshold)
    if config.strip_orphan_link_placeholders:
        out = _strip_orphan_link_placeholders(out)
    if config.strip_quoted_reply_chains:
        out = _strip_quoted_reply_chains(out)
    if config.strip_marketing_footers:
        out = _strip_marketing_footers(out)
    if config.collapse_whitespace:
        out = _collapse_whitespace(out)

    truncated = False
    if config.max_chars is not None and len(out) > config.max_chars:
        out = out[: config.max_chars]
        truncated = True
    return out, truncated


class _PlainTextExtractor(HTMLParser):
    """HTMLParser that ignores the contents of ``<style>`` / ``<script>`` blocks when asked."""

    _IGNORE_TAGS: frozenset[str] = frozenset({"style", "script"})

    def __init__(self, *, drop_style_and_script: bool) -> None:
        super().__init__()
        self._drop_style_and_script = drop_style_and_script
        self._parts: list[str] = []
        self._ignore_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if self._drop_style_and_script and tag.lower() in self._IGNORE_TAGS:
            self._ignore_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._drop_style_and_script and tag.lower() in self._IGNORE_TAGS and self._ignore_depth > 0:
            self._ignore_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignore_depth > 0:
            return
        if data:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def html_to_plain_text(
    html: str,
    config: NoiseFilterConfig = DEFAULT_NOISE_FILTER,
) -> str:
    """
    Parse ``html`` to plain text, optionally dropping ``<style>`` / ``<script>`` content,
    then run the result through :func:`filter_text_noise`.

    On a malformed document where ``HTMLParser`` raises, falls back to a regex tag-strip so
    the caller never sees an exception. Entity unescaping happens inside ``filter_text_noise``
    when the config flag is enabled (both the HTMLParser path and the regex fallback feed
    raw text that may still contain entities, e.g. when only some children parsed).
    """
    if not html or not str(html).strip():
        return ""

    parser = _PlainTextExtractor(drop_style_and_script=config.drop_html_style_and_script)
    try:
        parser.feed(html)
        parser.close()
        text = parser.text()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)

    filtered, _ = filter_text_noise(text, config)
    return filtered
