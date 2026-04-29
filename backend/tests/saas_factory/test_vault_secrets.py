"""Tests Phase 9-BOOT — security/vault_secrets.

Tests d'integration legers : on mocke `VaultClient` pour simuler le KV v2
Hashicorp sans demarrer un Vault reel.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.security.vault_secrets import (
    DEFAULT_ROTATION_DAYS,
    SecretNotFoundError,
    VaultSecrets,
    _aesgcm_decrypt,
    _aesgcm_encrypt,
    generate_envelope_key,
)


# ---------------------------------------------------------------------------
# AES-GCM pur
# ---------------------------------------------------------------------------
class TestAesGcm:
    def test_round_trip(self) -> None:
        key = generate_envelope_key()
        ct = _aesgcm_encrypt("hello world", key)
        assert ct.startswith("v1:")
        assert _aesgcm_decrypt(ct, key) == "hello world"

    def test_unique_ciphertext_for_same_plaintext(self) -> None:
        key = generate_envelope_key()
        a = _aesgcm_encrypt("same", key)
        b = _aesgcm_encrypt("same", key)
        # nonce aleatoire => ciphertexts different
        assert a != b
        assert _aesgcm_decrypt(a, key) == _aesgcm_decrypt(b, key) == "same"

    def test_wrong_key_fails(self) -> None:
        k1 = generate_envelope_key()
        k2 = generate_envelope_key()
        ct = _aesgcm_encrypt("secret", k1)
        with pytest.raises(Exception):
            _aesgcm_decrypt(ct, k2)

    def test_invalid_key_length_rejected(self) -> None:
        import base64
        bad = base64.urlsafe_b64encode(b"too-short").decode("ascii")
        with pytest.raises(ValueError):
            _aesgcm_encrypt("x", bad)

    def test_unsupported_version_rejected(self) -> None:
        key = generate_envelope_key()
        with pytest.raises(ValueError):
            _aesgcm_decrypt("v999:abc:def", key)

    def test_generated_key_is_32_bytes(self) -> None:
        import base64
        key = generate_envelope_key()
        raw = base64.urlsafe_b64decode(key)
        assert len(raw) == 32


# ---------------------------------------------------------------------------
# VaultSecrets — chemins put/get/rotate avec VaultClient mockee
# ---------------------------------------------------------------------------
def _fake_vault_client() -> MagicMock:
    """Simule un KV v2 in-memory."""
    store: dict[str, dict[str, str]] = {}
    client = MagicMock()
    client.get.side_effect = lambda path, default=None: dict(store.get(path, default or {}))

    def _put(path: str, data: dict[str, str]) -> None:
        store[path] = dict(data)
    client.put.side_effect = _put
    client.is_available.return_value = True
    client._store = store  # acces aux tests
    return client


class TestVaultSecretsPutGet:
    def test_put_then_get_round_trip_plaintext(self) -> None:
        client = _fake_vault_client()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VAULT_ENVELOPE_KEY", None)
            secrets_layer = VaultSecrets(client=client)
            stored = secrets_layer.put("anthropic", "api_key", "sk-ant-VALUE")
            assert stored.encrypted is False
            got = secrets_layer.get("anthropic", "api_key")
            assert got.value == "sk-ant-VALUE"
            assert got.encrypted is False
            assert got.rotation_interval_days == DEFAULT_ROTATION_DAYS

    def test_put_with_envelope_key_encrypts(self) -> None:
        client = _fake_vault_client()
        env_key = generate_envelope_key()
        with patch.dict(os.environ, {"VAULT_ENVELOPE_KEY": env_key}, clear=False):
            sec = VaultSecrets(client=client)
            sec.put("hostinger", "token", "tok-XYZ")
            # La valeur stockee dans Vault est chiffree
            raw = client._store["uba/hostinger" if False else "hostinger"]
            # client.put a recu le path 'hostinger' (sans prefixe car VaultClient
            # ajoute lui-meme le prefixe ; le mock ici stocke tel quel)
            assert raw["token__encrypted"] == "1"
            assert raw["token"] != "tok-XYZ"
            assert raw["token"].startswith("v1:")
            # get retourne la valeur en clair
            assert sec.get("hostinger", "token").value == "tok-XYZ"

    def test_refuse_empty_value(self) -> None:
        client = _fake_vault_client()
        sec = VaultSecrets(client=client)
        with pytest.raises(ValueError):
            sec.put("p", "k", "")

    def test_explicit_encrypt_without_envelope_key_raises(self) -> None:
        client = _fake_vault_client()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VAULT_ENVELOPE_KEY", None)
            sec = VaultSecrets(client=client)
            with pytest.raises(RuntimeError, match="VAULT_ENVELOPE_KEY"):
                sec.put("p", "k", "v", encrypt=True)


class TestVaultSecretsRotation:
    def test_needs_rotation_after_90_days(self) -> None:
        client = _fake_vault_client()
        sec = VaultSecrets(client=client)
        stored = sec.put("p", "k", "v1")
        # Pas encore expire
        assert stored.needs_rotation is False
        # Forcer une date passee
        old_iso = (datetime.now(UTC) - timedelta(days=91)).isoformat()
        client._store["p"]["k__rotated_at"] = old_iso
        # Note : VaultClient.get retourne un cache via dict.copy ;
        # le mock fait dict(store[path]), donc la mutation est visible.
        got = sec.get("p", "k")
        assert got.needs_rotation is True

    def test_rotate_replaces_value_and_resets_timestamp(self) -> None:
        client = _fake_vault_client()
        sec = VaultSecrets(client=client)
        sec.put("p", "k", "old")
        rotated = sec.rotate("p", "k", "new")
        assert rotated.value == "new"
        assert sec.get("p", "k").value == "new"

    def test_list_due_for_rotation_returns_only_overdue(self) -> None:
        client = _fake_vault_client()
        sec = VaultSecrets(client=client)
        sec.put("p1", "k", "fresh")
        sec.put("p2", "k", "stale")
        client._store["p2"]["k__rotated_at"] = (
            datetime.now(UTC) - timedelta(days=120)
        ).isoformat()
        due = sec.list_due_for_rotation()
        names = {s.path for s in due}
        assert "p2" in names
        assert "p1" not in names


class TestVaultSecretsFallback:
    def test_get_falls_back_to_env_when_secret_absent(self) -> None:
        client = _fake_vault_client()
        sec = VaultSecrets(client=client)
        with patch.dict(os.environ, {"FALLBACK_VAR": "from-env"}, clear=False):
            got = sec.get("missing", "key", fallback_env="FALLBACK_VAR")
            assert got.value == "from-env"
            assert got.encrypted is False

    def test_get_raises_when_no_secret_and_no_fallback(self) -> None:
        client = _fake_vault_client()
        sec = VaultSecrets(client=client)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MAYBE_VAR", None)
            with pytest.raises(SecretNotFoundError):
                sec.get("missing", "key")

    def test_get_handles_vault_exception_gracefully(self) -> None:
        client = _fake_vault_client()
        client.get.side_effect = RuntimeError("vault down")
        sec = VaultSecrets(client=client)
        with patch.dict(os.environ, {"FB": "from-env"}, clear=False):
            got = sec.get("p", "k", fallback_env="FB")
            assert got.value == "from-env"


class TestVaultSecretsLogging:
    def test_secret_value_never_appears_in_logs(self, caplog) -> None:
        client = _fake_vault_client()
        sec = VaultSecrets(client=client)
        with caplog.at_level("DEBUG"):
            sec.put("p", "k", "SUPER_SECRET_VALUE_42")
            sec.get("p", "k")
        for record in caplog.records:
            assert "SUPER_SECRET_VALUE_42" not in record.getMessage()
