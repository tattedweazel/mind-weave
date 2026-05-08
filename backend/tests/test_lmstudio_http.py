"""Tests for LM Studio URL / Bearer helpers."""

from app.core.config import settings
from app.providers.lmstudio_http import (
    lmstudio_origin_from_openai_base,
    normalize_bearer_secret_value,
    normalize_openai_base_url,
    resolve_lmstudio_bearer,
)


def test_normalize_openai_base_url_strips_slash():
    assert normalize_openai_base_url("http://x/v1/") == "http://x/v1"


def test_lmstudio_origin_from_openai_base():
    assert lmstudio_origin_from_openai_base("http://127.0.0.1:1234/v1") == "http://127.0.0.1:1234"
    assert lmstudio_origin_from_openai_base("http://127.0.0.1:1234") == "http://127.0.0.1:1234"


def test_resolve_prefers_user_key(monkeypatch):
    monkeypatch.setattr(settings, "LMSTUDIO_API_KEY", "env-key")
    assert resolve_lmstudio_bearer(decrypted_api_keys={"lmstudio_api_key": "user-key"}) == "user-key"


def test_resolve_env_fallback(monkeypatch):
    monkeypatch.setattr(settings, "LMSTUDIO_API_KEY", "env-key")
    assert resolve_lmstudio_bearer(decrypted_api_keys={}) == "env-key"


def test_resolve_empty_user_uses_env(monkeypatch):
    monkeypatch.setattr(settings, "LMSTUDIO_API_KEY", "env-key")
    assert resolve_lmstudio_bearer(decrypted_api_keys={"lmstudio_api_key": ""}) == "env-key"


def test_resolve_none_without_env(monkeypatch):
    monkeypatch.setattr(settings, "LMSTUDIO_API_KEY", "")
    assert resolve_lmstudio_bearer(decrypted_api_keys=None) is None


def test_resolve_ignores_stored_placeholder(monkeypatch):
    """Literal [stored] from a bad save must not be sent as Bearer (401 from LM Studio)."""
    monkeypatch.setattr(settings, "LMSTUDIO_API_KEY", "env-fallback")
    assert resolve_lmstudio_bearer(decrypted_api_keys={"lmstudio_api_key": "[stored]"}) == "env-fallback"


def test_resolve_strips_unicode_bom_from_pasted_key(monkeypatch):
    monkeypatch.setattr(settings, "LMSTUDIO_API_KEY", "")
    assert resolve_lmstudio_bearer(decrypted_api_keys={"lmstudio_api_key": "\ufeffmytoken"}) == "mytoken"


def test_normalize_bearer_secret_value_strips_bearer_prefixes():
    assert normalize_bearer_secret_value("  Bearer  tok  ") == "tok"
    assert normalize_bearer_secret_value("Bearer Bearer once") == "once"


def test_resolve_strips_bearer_prefix_from_user_key(monkeypatch):
    monkeypatch.setattr(settings, "LMSTUDIO_API_KEY", "env-fallback")
    assert (
        resolve_lmstudio_bearer(decrypted_api_keys={"lmstudio_api_key": "Bearer user-key"})
        == "user-key"
    )
