"""Unit tests for html_parse_basic.parse_html_basic (no I/O)."""

from typing import cast

import pytest
from bs4 import BeautifulSoup
from bs4.element import Tag

from app.domain.workflow_executor.html_parse_basic import (
    _container_has_excluded_for_wrapper,
    _is_direct_ol_or_ul_list_item,
    _is_strict_ancestor,
    _normalize_href,
    _omit_ancestor_rollups,
    _segment_by_granularity,
    _text_block_tag_included,
    _unwrap_backslash_quoted_href,
    parse_html_basic,
)


def _tb(*items: tuple[str, str]) -> list[dict[str, str]]:
    return [{"tag": t, "text": s} for t, s in items]


def _block_text_join(blocks: list[dict[str, str]]) -> str:
    return " ".join(b["text"] for b in blocks)


def test_empty_input_returns_empty_structure() -> None:
    assert parse_html_basic("") == {"title": "", "text_blocks": [], "links": []}
    assert parse_html_basic("   ") == {"title": "", "text_blocks": [], "links": []}


def test_empty_title_tag() -> None:
    out = parse_html_basic("<html><head><title></title></head><body></body></html>")
    assert out["title"] == ""
    assert out["text_blocks"] == []


def test_title_and_simple_blocks() -> None:
    html = "<html><head><title>Hello Title</title></head><body><p>First</p><p>Second</p></body></html>"
    out = parse_html_basic(html)
    assert out["title"] == "Hello Title"
    assert out["text_blocks"] == _tb(("p", "First"), ("p", "Second"))
    assert out["links"] == []
    assert "segment_text_blocks" not in out
    assert "parse_options" not in out


def test_nested_p_inside_div_emits_outer_div_only() -> None:
    html = "<html><body><div><p>inner</p></div><p>sib</p></body></html>"
    out = parse_html_basic(html)
    assert out["text_blocks"] == _tb(("p", "inner"), ("p", "sib"))


def test_links_text_and_href() -> None:
    html = (
        '<body><a href="  /path  ">  click  me  </a><a href="#">x</a>'
        '<a href="/img-only"><img src="a.png" alt=""></a><a href="/empty"></a></body>'
    )
    out = parse_html_basic(html)
    assert len(out["links"]) == 2
    assert out["links"][0] == {"text": "click me", "href": "/path"}
    assert out["links"][1] == {"text": "x", "href": "#"}


def test_unwrap_href_mismatched_backslash_runs_returns_none() -> None:
    # Same n on both sides is required: one backslash + quote at start, two + quote at end.
    asym = "\\" + '"' + "a" + "\\\\" + '"'
    assert _unwrap_backslash_quoted_href(asym) is None


def test_normalize_href_empty_after_strip() -> None:
    assert _normalize_href("  \n  ") == ""


def test_href_strips_backslash_quoted_and_entity_wrapped_values() -> None:
    # Literal \\" in markup (e.g. JSON-escaped HTML) — BS yields backslash+quote in the value.
    html_bs = r'<a href=\\\"index.html\\\">A</a>'
    # &quot; in attribute — value includes ASCII "…"  around the real path
    html_ent = (
        "<a href=\"&quot;catalogue/category/books/cultural_49/index.html&quot;\">B</a>"
    )
    out1 = parse_html_basic(html_bs)
    out2 = parse_html_basic(html_ent)
    assert out1["links"][0]["href"] == "index.html"
    assert out2["links"][0]["href"] == "catalogue/category/books/cultural_49/index.html"


def test_href_strips_single_quoted_path_when_only_wrap_chars() -> None:
    # Double-quoted href whose value is 'index.html' (apostrophes, no inner apostrophes)
    html = """<a href=\"'index.html'\">C</a>"""
    out = parse_html_basic(html)
    assert out["links"][0]["href"] == "index.html"


def test_malformed_html_best_effort() -> None:
    out = parse_html_basic("<div><p>ok</div>")
    assert "title" in out and "text_blocks" in out and "links" in out
    assert isinstance(out["text_blocks"], list)


def test_section_article_order() -> None:
    html = "<body><section>A</section><article>B</article></body>"
    out = parse_html_basic(html)
    assert out["text_blocks"] == _tb(("section", "A"), ("article", "B"))


def test_newlines_and_nbsp_collapsed_to_spaces() -> None:
    html = (
        "<html><head><title> T1 \n </title></head><body>"
        "<p>Line1\nLine2\tMore</p><p>foo&nbsp;bar&#x00a0;baz</p>"
        "</body></html>"
    )
    out = parse_html_basic(html)
    assert "\n" not in out["title"]
    assert out["title"] == "T1"
    assert out["text_blocks"] == _tb(("p", "Line1 Line2 More"), ("p", "foo bar baz"))
    assert "\u00a0" not in _block_text_join(out["text_blocks"])


def test_link_text_strips_nbsp_and_newlines() -> None:
    html = '<a href="/x">One\nTwo\u00a0Three</a>'
    out = parse_html_basic(html)
    assert out["links"][0]["text"] == "One Two Three"


def test_text_blocks_decode_literal_slash_u_as_character() -> None:
    # Scraped/minified content often carries ``\u00a3`` as plain text, not ``&pound;``.
    html = "<p>Price " + "\\" + "u00a3" + " 5</p>"
    out = parse_html_basic(html)
    assert out["text_blocks"] == _tb(("p", "Price £ 5"))


def test_script_and_style_not_in_text_blocks() -> None:
    html = """<body><div id="main"><p>Hello</p>
    <script>const x = 1;\\n\\n\\n\\n</script>
    <style> .x { display: block; } </style>
    </div></body>"""
    out = parse_html_basic(html)
    assert out["text_blocks"] == _tb(("p", "Hello"))
    assert "const" not in _block_text_join(out["text_blocks"])
    assert "display" not in _block_text_join(out["text_blocks"]).lower()


def test_literal_backslash_n_sequences_collapsed() -> None:
    html = r"<body><div><p>foo\n\nbar</p></div></body>"
    out = parse_html_basic(html)
    assert "\n" not in out["text_blocks"][0]["text"]
    assert "\\" not in out["text_blocks"][0]["text"]
    assert out["text_blocks"][0] == {"tag": "p", "text": "foo bar"}


def test_content_root_css_scopes_blocks_and_links_title_from_full_doc() -> None:
    html = (
        "<html><head><title>Page T</title></head><body>"
        '<div id="nav"><a href="/n">N</a></div>'
        '<main id="m"><p>Core</p><a href="/c">C</a></main>'
        "</body></html>"
    )
    out = parse_html_basic(html, content_root_css="#m")
    assert out["title"] == "Page T"
    assert out["text_blocks"] == _tb(("p", "Core"))
    assert out["links"] == [{"text": "C", "href": "/c"}]


def test_list_items_granularity_adds_segments() -> None:
    html = (
        "<body><div><ul><li>  One  </li><li>Two</li></ul>"
        "<ol><li>Third</li></ol></div></body>"
    )
    out = parse_html_basic(html, granularity="list_items")
    assert out["text_blocks"]  # from outer div
    assert out["segment_text_blocks"] == ["One", "Two", "Third"]
    assert out["parse_options"] == {
        "granularity": "list_items",
        "content_root_css": None,
    }
    assert "parse_options" in out and out["parse_options"]["granularity"] == "list_items"


def test_articles_granularity() -> None:
    html = "<body><article> <p>A1</p> </article><article><p>A2</p></article></body>"
    out = parse_html_basic(html, granularity="articles")
    assert out["segment_text_blocks"] == ["A1", "A2"]
    assert out["parse_options"]["granularity"] == "articles"


def test_content_root_with_list_items() -> None:
    html = (
        "<body><div id='out'><ul><li>Skip</li></ul></div>"
        "<div id='in'><ul><li>Keep</li></ul></div></body>"
    )
    out = parse_html_basic(html, content_root_css="#in", granularity="list_items")
    assert out["segment_text_blocks"] == ["Keep"]


def test_invalid_content_root_css_raises() -> None:
    with pytest.raises(ValueError, match="matched no element"):
        parse_html_basic("<html><body><p>x</p></body></html>", content_root_css="#nope")


def test_invalid_granularity_raises() -> None:
    with pytest.raises(ValueError, match="unknown granularity"):
        parse_html_basic("<p>a</p>", granularity="lobster")


def test_coarse_granularity_same_as_default() -> None:
    out = parse_html_basic("<p>a</p>", granularity="coarse")
    assert out == parse_html_basic("<p>a</p>")
    assert "segment_text_blocks" not in out


def test_segment_by_granularity_default_returns_empty() -> None:
    soup = BeautifulSoup("<ul><li>x</li></ul>", "html.parser")
    assert _segment_by_granularity(soup, "default") == []


def test_list_item_not_under_ol_or_ul_is_skipped() -> None:
    out = parse_html_basic("<html><body><li>orphan</li><p>ok</p></body></html>")
    assert "orphan" not in _block_text_join(out["text_blocks"])
    assert any(b["text"] == "ok" for b in out["text_blocks"])


def test_non_leaf_outer_article_omitted_inner_emitted() -> None:
    out = parse_html_basic(
        "<html><body><article>outer<article>INNER</article></article></body></html>"
    )
    assert out["text_blocks"] == _tb(("article", "INNER"))


def test_heading_inside_article_omitted_outside_kept() -> None:
    out = parse_html_basic(
        "<html><body><article><h2>in</h2></article><h1>out</h1></body></html>"
    )
    assert out["text_blocks"] == _tb(("article", "in"), ("h1", "out"))


def test_direct_list_item_helper_rejects_non_li() -> None:
    soup = BeautifulSoup("<p>x</p>", "html.parser")
    p = soup.find("p")
    assert p is not None
    assert _is_direct_ol_or_ul_list_item(cast(Tag, p)) is False


def test_why_container_helper_rejects_non_structural_tag() -> None:
    soup = BeautifulSoup("<p>x</p>", "html.parser")
    p = soup.find("p")
    assert p is not None
    assert _container_has_excluded_for_wrapper(cast(Tag, p)) is True


def test_container_excludes_when_descendants_carry_text() -> None:
    assert _container_has_excluded_for_wrapper(
        cast(Tag, BeautifulSoup("<div><article>x</article></div>", "html.parser").find("div"))
    )
    assert _container_has_excluded_for_wrapper(
        cast(Tag, BeautifulSoup("<div><h3>x</h3></div>", "html.parser").find("div"))
    )
    assert _container_has_excluded_for_wrapper(
        cast(Tag, BeautifulSoup("<div><div>x</div></div>", "html.parser").find("div"))
    )
    assert _container_has_excluded_for_wrapper(
        cast(Tag, BeautifulSoup("<section><section>x</section></section>", "html.parser").find("section"))
    )
    assert _container_has_excluded_for_wrapper(
        cast(Tag, BeautifulSoup("<div><section>x</section></div>", "html.parser").find("div"))
    )
    assert _container_has_excluded_for_wrapper(
        cast(Tag, BeautifulSoup("<div><main>x</main></div>", "html.parser").find("div"))
    )
    assert _container_has_excluded_for_wrapper(
        cast(Tag, BeautifulSoup("<main><div>x</div></main>", "html.parser").find("main"))
    )


def test_li_with_child_article_defers_to_leaf_article() -> None:
    out = parse_html_basic("<body><ul><li><article>card</article></li></ul></body>")
    assert out["text_blocks"] == _tb(("article", "card"))


def test_text_block_tag_included_false_for_unlisted_tag() -> None:
    soup = BeautifulSoup("<b>bold</b>", "html.parser")
    b = soup.find("b")
    assert b is not None
    assert _text_block_tag_included(cast(Tag, b)) is False


def test_omit_ancestor_rollups_empty_list() -> None:
    assert _omit_ancestor_rollups([]) == []


def test_is_strict_ancestor_detects_nested_li() -> None:
    soup = BeautifulSoup(
        "<ul><li>outer<ul><li>inner</li></ul></li></ul>",
        "html.parser",
    )
    outer_li = soup.find("ul").find("li", recursive=False)
    inner_li = soup.find("ul").find("ul").find("li")
    assert outer_li is not None and inner_li is not None
    assert _is_strict_ancestor(cast(Tag, outer_li), cast(Tag, inner_li)) is True
    assert _is_strict_ancestor(cast(Tag, inner_li), cast(Tag, outer_li)) is False


def test_ancestor_rollup_suppresses_parent_li_with_nested_lis() -> None:
    html = (
        "<ul>"
        "<li>Books<ul><li>Travel</li><li>Mystery</li></ul></li>"
        "</ul>"
    )
    out = parse_html_basic(html)
    assert out["text_blocks"] == _tb(("li", "Travel"), ("li", "Mystery"))
    assert "Books Travel Mystery" not in _block_text_join(out["text_blocks"])


def test_ancestor_rollup_suppresses_parent_li_for_child_paragraphs() -> None:
    out = parse_html_basic("<ul><li><p>a</p><p>b</p></li></ul>")
    assert out["text_blocks"] == _tb(("p", "a"), ("p", "b"))


def test_nested_div_siblings_not_rolled_into_parent_when_parent_excluded() -> None:
    """Outer div has child divs, so _container skips outer; inners remain (no mega parent string)."""
    out = parse_html_basic(
        "<body><div><div>Books</div><div>Travel</div><div>Mystery</div></div></body>"
    )
    assert out["text_blocks"] == _tb(
        ("div", "Books"), ("div", "Travel"), ("div", "Mystery")
    )
