"""Deterministic HTML → structured data for the ``html_parse_basic`` utility (BeautifulSoup, no I/O)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union, cast

from bs4 import BeautifulSoup, PageElement, Tag

from app.core.text_noise import NoiseFilterConfig, filter_text_noise

_GRANULARITY_DEFAULT = "default"
_HEADING_TAG_NAMES: tuple[str, ...] = tuple(f"h{i}" for i in range(1, 7))
# Tags considered for document-order text blocks (plus ``li`` when ``ol > li`` / ``ul > li``).
_TEXT_BLOCK_CANDIDATE_TAGS: tuple[str, ...] = (
    "article",
    *_HEADING_TAG_NAMES,
    "p",
    "div",
    "section",
    "main",
    "li",
)
# Values accepted for ``granularity`` after normalisation (lowercase, stripped).
_KNOWN_GRANULARITY = frozenset(
    {
        "default",
        "list_items",
        "articles",
    }
)

# Entity + invisible-Unicode only; we collapse whitespace here so we never keep internal
# newlines from the noise filter’s collapse pass.
_HTML_PARSE_TEXT_FILTER = NoiseFilterConfig(
    drop_html_style_and_script=False,
    strip_repeated_separators=False,
    strip_tracking_url_params=False,
    shorten_long_urls=False,
    strip_orphan_link_placeholders=False,
    strip_quoted_reply_chains=False,
    strip_marketing_footers=False,
    collapse_whitespace=False,
    max_chars=None,
)

# Two-character “\n” / “\r” / … in page text (not a real U+000A newline)
_RE_LITERAL_ESCAPE = re.compile(r"\\[nrtf]")


def _unwrap_backslash_quoted_href(s: str) -> str | None:
    """
    If ``s`` is ``n`` backslashes, an opening ``"``, ``mid``, ``n`` backslashes, and a
    closing ``"`` (``n`` ≥ 1, same on both sides), return ``mid``.

    A greedy ``.*`` pattern must not be used: for ``n > 1``, it can leave backslashes in mid.
    """
    if not s or len(s) < 4 or s[-1] != '"':
        return None
    n = 0
    while n < len(s) and s[n] == "\\":
        n += 1
    if n < 1 or s[n] != '"':
        return None
    t = 0
    j = len(s) - 2
    while j >= 0 and s[j] == "\\":
        t += 1
        j -= 1
    if t != n:
        return None
    return s[n + 1 : len(s) - t - 1]


def _normalize_href(href: str) -> str:
    """
    Clean hrefs that are over-quoted from the parser or from ``&quot;``-style attributes.

    BeautifulSoup can yield a run of backslashes and ``"`` on each end of the value, or ASCII
    double/single quotes (from ``&quot;`` / similar) as the whole value. Unwrap matching outer
    layers only.
    """
    s = (href or "").strip()
    if not s:
        return ""
    for _ in range(8):
        before = s
        unwrapped = _unwrap_backslash_quoted_href(s)
        if unwrapped is not None:
            s = unwrapped.strip()
        # A single pair of double quotes and no other ``"`` inside
        elif len(s) >= 2 and s[0] == s[-1] == '"' and s.count('"') == 2:
            s = s[1:-1].strip()
        # Same for a single pair of single quotes, no other ``'`` inside
        elif len(s) >= 2 and s[0] == s[-1] == "'" and s.count("'") == 2:
            s = s[1:-1].strip()
        if s == before:
            break
    return s


def _remove_non_rendering_tags(soup: BeautifulSoup) -> None:
    """Remove tags so ``get_text`` does not pull script/style bodies into blocks."""
    for t in list(soup.find_all(["script", "style", "noscript", "template"])):
        t.decompose()


def _clean_extracted_text(s: str) -> str:
    if not s:
        return ""
    out, _ = filter_text_noise(s, _HTML_PARSE_TEXT_FILTER)
    for ch in ("\ufeff", "\u0085", "\u2028", "\u2029"):
        out = out.replace(ch, " ")
    out = _RE_LITERAL_ESCAPE.sub(" ", out)
    out = re.sub(r"[\n\r\x0b\x0c\u0085\u2028\u2029]+", " ", out)
    return re.sub(r"\s+", " ", out).strip()


def _is_inside_any_article(tag: Tag) -> bool:
    for parent in tag.parents:
        if (parent.name or "").lower() == "article":
            return True
    return False


def _is_leaf_article(tag: Tag) -> bool:
    """A product card, blog post, or similar: no nested ``article`` (avoid parent/child duplication)."""
    return not tag.find("article", recursive=True)


def _parent_is_p(tag: Tag) -> bool:
    p = tag.parent
    return bool(p and (p.name or "").lower() == "p")


def _is_direct_ol_or_ul_list_item(tag: Tag) -> bool:
    if (tag.name or "").lower() != "li":
        return False
    p = tag.parent
    return bool(p and (p.name or "").lower() in ("ol", "ul"))


def _container_has_excluded_for_wrapper(tag: Tag) -> bool:
    """
    If true, a ``div``/``section``/``main`` is not emitted as a single wrapper block: descendants
    carry the text (``article`` cards, ``p``, headings, lists, or nested block shells).
    """
    n = (tag.name or "").lower()
    if n not in ("div", "section", "main"):
        return True
    if tag.find("article", recursive=True):
        return True
    for hn in _HEADING_TAG_NAMES:
        if tag.find(hn, recursive=True):
            return True
    if tag.find("p", recursive=True) or tag.find("ol", recursive=True) or tag.find("ul", recursive=True):
        return True
    if n == "div" and tag.find("div", recursive=True):
        return True
    if n == "section" and tag.find("section", recursive=True):
        return True
    if n == "div" and (tag.find("section", recursive=True) or tag.find("main", recursive=True)):
        return True
    if n == "main" and (tag.find("div", recursive=True) or tag.find("section", recursive=True)):
        return True
    return False


def _normalise_granularity(raw: Optional[str]) -> str:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return _GRANULARITY_DEFAULT
    g = str(raw).strip().lower()
    if g in ("default", "coarse"):
        return _GRANULARITY_DEFAULT
    if g in _KNOWN_GRANULARITY:
        return g
    raise ValueError(
        f"html_parse_basic: unknown granularity {raw!r}; expected 'default', 'list_items', or 'articles'."
    )


def _resolve_work_root(
    soup: BeautifulSoup, content_root_css: Optional[str]
) -> Union[BeautifulSoup, Tag]:
    c = (content_root_css or "").strip()
    if not c:
        return soup
    el = soup.select_one(c)
    if el is None:
        raise ValueError(f"html_parse_basic: content_root_css {c!r} matched no element")
    return el


def _text_block_tag_included(tag: Tag) -> bool:
    name = (tag.name or "").lower()
    if name == "li" and not _is_direct_ol_or_ul_list_item(tag):
        return False
    if name == "article":
        return _is_leaf_article(tag)
    if name in _HEADING_TAG_NAMES:
        return not _is_inside_any_article(tag)
    if name == "p":
        return not _is_inside_any_article(tag) and not _parent_is_p(tag)
    if name == "li":
        return not _is_inside_any_article(tag) and not bool(tag.find("article", recursive=True))
    if name in ("div", "section", "main"):
        return not _is_inside_any_article(tag) and not _container_has_excluded_for_wrapper(tag)
    return False


def _is_strict_ancestor(ancestor: Tag, descendant: Tag) -> bool:
    p: PageElement | None = descendant.parent
    while p is not None:
        if p is ancestor:
            return True
        p = p.parent
    return False


def _omit_ancestor_rollups(ordered_with_text: List[Tag]) -> List[Tag]:
    if not ordered_with_text:
        return []
    drop_ids: set[int] = set()
    for a in ordered_with_text:
        for c in ordered_with_text:
            if c is a:
                continue
            if _is_strict_ancestor(a, c):
                drop_ids.add(id(a))
                break
    return [t for t in ordered_with_text if id(t) not in drop_ids]


def _iter_outer_block_text(work: PageElement) -> List[Dict[str, str]]:
    """
    Build ``text_blocks`` in document order: each item is ``{"tag": <element name>, "text": ...}`` for
    **leaf** ``article``s, headings, ``p``, list items, and pure ``div``/``section``/``main`` wrappers
    (per ``_container_has_excluded_for_wrapper``), then drop any candidate that is a strict
    ancestor of another kept candidate (no parent “rollup” when children are emitted).
    """
    candidates: List[Tag] = []
    for tag in work.find_all(list(_TEXT_BLOCK_CANDIDATE_TAGS)):
        t = cast(Tag, tag)
        if not _text_block_tag_included(t):
            continue
        candidates.append(t)
    with_text = [
        t
        for t in candidates
        if _clean_extracted_text(t.get_text(separator=" ", strip=True))
    ]
    kept = _omit_ancestor_rollups(with_text)
    out: List[Dict[str, str]] = []
    for t in kept:
        name = (t.name or "").lower()
        out.append(
            {
                "tag": name,
                "text": _clean_extracted_text(t.get_text(separator=" ", strip=True)),
            }
        )
    return out


def _extract_links_from(work: PageElement) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    for a in work.find_all("a", href=True):
        a = cast(Tag, a)
        raw = a.get("href")
        href = _normalize_href(str(raw).strip() if raw is not None else "")
        text = _clean_extracted_text(a.get_text(separator=" ", strip=True))
        if not text:
            continue
        links.append({"text": text, "href": href})
    return links


def _segment_by_granularity(work: PageElement, granularity: str) -> List[str]:
    if granularity == "list_items":
        segs: List[str] = []
        for li in work.select("ol > li, ul > li"):
            li = cast(Tag, li)
            t = _clean_extracted_text(li.get_text(separator=" ", strip=True))
            if t:
                segs.append(t)
        return segs
    if granularity == "articles":
        segs2: List[str] = []
        for ar in work.find_all("article", recursive=True):
            ar = cast(Tag, ar)
            t = _clean_extracted_text(ar.get_text(separator=" ", strip=True))
            if t:
                segs2.append(t)
        return segs2
    return []


def parse_html_basic(
    html: str,
    *,
    granularity: Optional[str] = None,
    content_root_css: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return ``title`` from the full document, then ``text_blocks`` and ``links`` from the work root
    (entire document or the subtree selected by ``content_root_css``). ``text_blocks`` is a list of
    ``{"tag": "<name>", "text": "..."}`` objects (lowercased source element name plus normalized text),
    in document order, using leaf ``article`` nodes, headings, paragraphs, and list items so typical
    listing pages (e.g. ``<article class="product_pod">`` grids) do not collapse to one or two
    top-level ``div`` strings. A second structural pass **drops** any candidate that is a strict
    ancestor of another emitted block (avoids a parent ``li``/container string duplicating child
    blocks). ``links`` omit anchors whose visible text is empty after cleaning (common for image-only
    links).

    When ``granularity`` is ``list_items`` or ``articles``, add ``segment_text_blocks`` and
    ``parse_options``; for ``default`` / omitted, only ``title``, ``text_blocks``, and ``links`` are
    returned.

    May raise ``ValueError`` for unknown ``granularity`` or when ``content_root_css`` matches
    nothing in the document.
    """
    s = (html or "").strip()
    if not s:
        return {"title": "", "text_blocks": [], "links": []}

    g = _normalise_granularity(granularity)
    soup = BeautifulSoup(s, "html.parser")
    _remove_non_rendering_tags(soup)

    title = ""
    title_el = soup.find("title")
    if title_el and isinstance(title_el, Tag):
        title = _clean_extracted_text(title_el.get_text())

    work = _resolve_work_root(soup, content_root_css)
    text_blocks = _iter_outer_block_text(work)
    links = _extract_links_from(work)

    out: Dict[str, Any] = {"title": title, "text_blocks": text_blocks, "links": links}
    if g != _GRANULARITY_DEFAULT:
        out["segment_text_blocks"] = _segment_by_granularity(work, g)
        out["parse_options"] = {
            "granularity": g,
            "content_root_css": (content_root_css or "").strip() or None,
        }
    return out
