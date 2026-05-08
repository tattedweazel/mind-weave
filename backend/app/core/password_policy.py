"""Shared password rules (SE-013)."""

import re

_MIN_LEN = 12
_MAX_LEN = 256


def validate_password_strength(password: str) -> str:
    if len(password) < _MIN_LEN or len(password) > _MAX_LEN:
        raise ValueError(f"Password must be between {_MIN_LEN} and {_MAX_LEN} characters")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ValueError("Password must contain at least one letter and one number")
    return password
