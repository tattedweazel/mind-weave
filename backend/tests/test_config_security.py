"""Settings validation for SE-001 / SE-002."""

import pytest

from app.core.config import _DEV_SECRET_PLACEHOLDER, Settings


def test_local_accepts_dev_placeholder_secret():
    s = Settings(APP_ENV="local", SECRET_KEY=_DEV_SECRET_PLACEHOLDER)
    assert s.SECRET_KEY == _DEV_SECRET_PLACEHOLDER


def test_lmstudio_chat_timeout_default_one_hour() -> None:
    """Code default is 3600s when no `.env` is loaded (developer `.env` often overrides)."""
    s = Settings(
        _env_file=None,
        APP_ENV="local",
        SECRET_KEY=_DEV_SECRET_PLACEHOLDER,
    )
    assert s.LMSTUDIO_CHAT_TIMEOUT == 3600.0


def test_lmstudio_aux_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LMSTUDIO_API_KEY", raising=False)
    s = Settings(
        _env_file=None,
        APP_ENV="local",
        SECRET_KEY=_DEV_SECRET_PLACEHOLDER,
    )
    assert s.LMSTUDIO_API_KEY == ""
    assert s.LMSTUDIO_MODEL_LOAD_TIMEOUT == 300.0
    assert s.LMSTUDIO_CHAT_RETRY_BUDGET_SECONDS == 120.0


def test_behind_reverse_proxy_defaults_false() -> None:
    s = Settings(
        _env_file=None,
        APP_ENV="local",
        SECRET_KEY=_DEV_SECRET_PLACEHOLDER,
    )
    assert s.BEHIND_REVERSE_PROXY is False


def test_behind_reverse_proxy_can_be_true() -> None:
    s = Settings(
        _env_file=None,
        APP_ENV="local",
        SECRET_KEY=_DEV_SECRET_PLACEHOLDER,
        BEHIND_REVERSE_PROXY=True,
    )
    assert s.BEHIND_REVERSE_PROXY is True


def test_local_rejects_short_secret():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(APP_ENV="local", SECRET_KEY="short")


def test_production_rejects_placeholder_secret():
    with pytest.raises(ValueError, match="placeholder"):
        Settings(APP_ENV="production", SECRET_KEY=_DEV_SECRET_PLACEHOLDER)


def test_production_rejects_short_secret():
    with pytest.raises(ValueError, match="32"):
        Settings(APP_ENV="production", SECRET_KEY="x" * 31)


def test_production_accepts_long_random_secret():
    secret = "x" * 32
    s = Settings(APP_ENV="production", SECRET_KEY=secret)
    assert s.SECRET_KEY == secret


def test_bootstrap_admin_forbidden_outside_local():
    with pytest.raises(ValueError, match="BOOTSTRAP_DEFAULT_ADMIN"):
        Settings(
            APP_ENV="production",
            SECRET_KEY="x" * 32,
            BOOTSTRAP_DEFAULT_ADMIN=True,
        )


def test_settings_rejects_invalid_rate_limit_spec():
    with pytest.raises(ValueError, match="AUTH_LOGIN_RATE_LIMIT"):
        Settings(
            APP_ENV="local",
            SECRET_KEY="pytest-secret-key-at-least-sixteen-characters",
            AUTH_LOGIN_RATE_LIMIT="not-a-valid-limit",
        )
