"""Tests for api_keys at-rest encryption."""

from app.core.user_api_keys_crypto import decrypt_api_keys_store, encrypt_api_keys_store


def test_decrypt_omits_v1_blob_when_decrypt_fails_instead_of_using_ciphertext():
    """InvalidToken must not yield the encrypted string as the "secret" (would cause LM Studio 401)."""
    enc = encrypt_api_keys_store({"openai": "sk-secret"})
    raw = enc["openai"]
    assert raw.startswith("v1.")
    corrupted = raw[:-3] + "XXX"
    out = decrypt_api_keys_store({"openai": corrupted})
    assert "openai" not in out


def test_decrypt_round_trip():
    enc = encrypt_api_keys_store({"lmstudio_api_key": "tok"})
    assert decrypt_api_keys_store(enc) == {"lmstudio_api_key": "tok"}
