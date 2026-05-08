"""Unit tests for ``document_metadata_service.compute_document_metadata``."""

from app.domain.services.document_metadata_service import (
    TOKENIZER_NAME,
    compute_document_metadata,
)


def test_empty_body_returns_zeros():
    stats = compute_document_metadata("")
    assert stats.token_count == 0
    assert stats.character_count == 0
    assert stats.word_count == 0
    assert stats.line_count == 0


def test_simple_ascii_body_counts_match():
    body = "Hello, world!"
    stats = compute_document_metadata(body)
    assert stats.character_count == len(body)
    assert stats.word_count == 2
    assert stats.line_count == 1
    assert stats.token_count > 0


def test_multiline_body_counts_lines_correctly():
    body = "alpha\nbeta\ngamma"
    stats = compute_document_metadata(body)
    assert stats.line_count == 3
    assert stats.word_count == 3
    assert stats.character_count == len(body)
    assert stats.token_count >= 3


def test_single_newline_terminator_does_not_inflate_line_count():
    # ``str.splitlines()`` returns 1 segment for "a\n"; we keep that semantic.
    stats = compute_document_metadata("alpha\n")
    assert stats.line_count == 1


def test_whitespace_only_body_has_no_words_but_has_chars():
    stats = compute_document_metadata("   \t  ")
    assert stats.word_count == 0
    assert stats.character_count == 6
    assert stats.line_count >= 1


def test_multibyte_unicode_chars_are_counted_by_codepoint():
    body = "café"
    stats = compute_document_metadata(body)
    assert stats.character_count == 4
    assert stats.token_count > 0


def test_repeated_calls_use_cached_encoding():
    # Multiple calls should not re-load the tokenizer (the @lru_cache(maxsize=1)
    # in the service guarantees this); we just assert results stay consistent.
    a = compute_document_metadata("token consistency")
    b = compute_document_metadata("token consistency")
    assert a == b


def test_tokenizer_name_constant_is_o200k_base():
    assert TOKENIZER_NAME == "o200k_base"
