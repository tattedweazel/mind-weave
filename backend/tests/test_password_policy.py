import pytest

from app.core.password_policy import validate_password_strength


def test_validate_password_accepts_strong():
    assert validate_password_strength("GoodPassword123") == "GoodPassword123"


def test_validate_password_rejects_short():
    with pytest.raises(ValueError, match="12"):
        validate_password_strength("short1")


def test_validate_password_requires_letter_and_digit():
    with pytest.raises(ValueError, match="letter"):
        validate_password_strength("alllettersnopass")
