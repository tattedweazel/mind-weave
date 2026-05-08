"""End-to-end checks: save (encrypt) → load (decrypt) → Bearer header.

These tests lock the three areas the user asked about:
1. Persisting the submitted token (merge + Fernet encrypt)
2. Reading it back (decrypt_api_keys_store)
3. Sending to LM Studio (resolve_lmstudio_bearer + bearer_auth_headers)
"""

from app.api.v1.auth import _merge_api_keys_update
from app.core.user_api_keys_crypto import decrypt_api_keys_store
from app.providers.lmstudio_http import bearer_auth_headers, resolve_lmstudio_bearer


def test_lmstudio_api_key_round_trip_merge_decrypt_resolve_matches_saved_plaintext():
    """What you PUT as lmstudio_api_key (after normalization) is exactly what Bearer uses."""
    plain = "exact-lm-token-for-round-trip"
    persisted = _merge_api_keys_update(None, {"lmstudio_api_key": plain})
    assert persisted["lmstudio_api_key"].startswith("v1.")

    decrypted = decrypt_api_keys_store(persisted)
    assert decrypted["lmstudio_api_key"] == plain

    token = resolve_lmstudio_bearer(decrypted_api_keys=decrypted)
    assert token == plain

    assert bearer_auth_headers(token) == {"Authorization": f"Bearer {plain}"}


def test_lmstudio_api_key_merge_persists_normalized_value_then_decrypts_same():
    """Bearer prefix is stripped before encrypt; decrypt yields the token LM Studio expects."""
    persisted = _merge_api_keys_update(None, {"lmstudio_api_key": "Bearer  tok-after-strip  "})
    assert decrypt_api_keys_store(persisted)["lmstudio_api_key"] == "tok-after-strip"
    assert resolve_lmstudio_bearer(decrypted_api_keys=decrypt_api_keys_store(persisted)) == "tok-after-strip"


def test_lmstudio_api_key_merge_on_top_of_existing_preserves_other_keys():
    """Incremental merge re-encrypts merged plaintext; other keys still decrypt."""
    s1 = _merge_api_keys_update(None, {"openai": "sk-openai-only"})
    s2 = _merge_api_keys_update(s1, {"lmstudio_api_key": "lm-only"})
    dec = decrypt_api_keys_store(s2)
    assert dec["openai"] == "sk-openai-only"
    assert dec["lmstudio_api_key"] == "lm-only"
    assert resolve_lmstudio_bearer(decrypted_api_keys=dec) == "lm-only"
