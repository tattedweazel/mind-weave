"""Logging filters — Authorization header redaction (SE-026)."""

import logging

from app.core.logging import _RedactAuthorizationFilter


def test_redact_authorization_filter_masks_bearer_token():
    filt = _RedactAuthorizationFilter()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Authorization: Bearer super-secret-token-value",
        args=(),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert "super-secret-token-value" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_redact_authorization_filter_case_insensitive_header_name():
    filt = _RedactAuthorizationFilter()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="authorization: bearer abc.def.ghi",
        args=(),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert "abc.def.ghi" not in record.getMessage()
