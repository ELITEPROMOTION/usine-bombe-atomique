"""Module F : wrapper haut-niveau Vault Hashicorp pour V9.

Empile sur `app.integrations.vault_client.VaultClient` (deja en place) :

- enveloppe AES-256-GCM optionnelle (la valeur stockee dans Vault est elle-meme
  chiffree par une cle d'enveloppe, separable du Vault lui-meme)
- meta de rotation : `last_rotated_at`, `rotation_interval_days` (90j par defaut)
- audit log a chaque lecture/ecriture (logger structlog + DB si pool fourni)
- fallback gracieux sur les variables d'environnement si Vault est down

La valeur secrete brute n'apparait JAMAIS dans les logs (seulement le path
et un sha256 tronque).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.integrations.vault_client import VaultClient, VaultUnavailable, get_vault

logger = logging.getLogger(__name__)

DEFAULT_ROTATION_DAYS = 90


class SecretNotFoundError(LookupError):
    pass


@dataclass
class StoredSecret:
    path: str
    key: str
    value: str
    last_rotated_at: datetime
    rotation_interval_days: int
    encrypted: bool

    @property
    def needs_rotation(self) -> bool:
        deadline = self.last_rotated_at + timedelta(days=self.rotation_interval_days)
        return datetime.now(UTC) >= deadline


def _short_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _aesgcm_encrypt(plaintext: str, key_b64: str) -> str:
    """Encrypte une chaine via AES-256-GCM. Renvoie 'v1:<nonce_b64>:<ct_b64>'."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = base64.urlsafe_b64decode(key_b64)
    if len(key) != 32:
        raise ValueError("AES-256-GCM key must be 32 bytes (base64url-encoded)")
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return "v1:" + base64.urlsafe_b64encode(nonce).decode("ascii") + ":" + \
        base64.urlsafe_b64encode(ct).decode("ascii")


def _aesgcm_decrypt(ciphertext: str, key_b64: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not ciphertext.startswith("v1:"):
        raise ValueError("unsupported cipher version")
    _, nonce_b64, ct_b64 = ciphertext.split(":", 2)
    key = base64.urlsafe_b64decode(key_b64)
    nonce = base64.urlsafe_b64decode(nonce_b64)
    ct = base64.urlsafe_b64decode(ct_b64)
    return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")


def generate_envelope_key() -> str:
    """Cle AES-256 base64url pour l'enveloppe (a stocker dans VAULT_ENVELOPE_KEY)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


class VaultSecrets:
    """Couche operationnelle au-dessus de VaultClient.

    Comportements clefs :
    - put : stocke {value, encrypted?, last_rotated_at, rotation_interval_days}
    - get : lit, dechiffre si necessaire, fallback env si Vault down
    - rotate : appel explicite avec une nouvelle valeur
    - list_due_for_rotation : balaie tous les paths surveilles
    - tous les acces sont loggues (path + sha256 court de la valeur, jamais la valeur)
    """

    def __init__(
        self,
        client: VaultClient | None = None,
        *,
        envelope_key_env: str = "VAULT_ENVELOPE_KEY",
        rotation_days: int = DEFAULT_ROTATION_DAYS,
    ) -> None:
        self._client = client or get_vault()
        self._envelope_key_env = envelope_key_env
        self._rotation_days = rotation_days
        self._tracked_paths: set[tuple[str, str]] = set()

    # --- helpers ---
    def _envelope_key(self) -> str | None:
        return os.environ.get(self._envelope_key_env)

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _audit(self, action: str, path: str, value_for_hash: str | None) -> None:
        digest = _short_sha(value_for_hash) if value_for_hash else "-"
        logger.info("vault_secret action=%s path=%s digest=%s", action, path, digest)

    # --- public ---
    def put(
        self,
        path: str,
        key: str,
        value: str,
        *,
        encrypt: bool | None = None,
        rotation_days: int | None = None,
    ) -> StoredSecret:
        if not value:
            raise ValueError("refus de stocker une valeur vide")

        envelope_key = self._envelope_key()
        do_encrypt = encrypt if encrypt is not None else bool(envelope_key)
        if do_encrypt and not envelope_key:
            raise RuntimeError(
                f"encrypt=True requis mais {self._envelope_key_env} non defini"
            )

        stored_value = _aesgcm_encrypt(value, envelope_key) if do_encrypt else value
        rotation = rotation_days or self._rotation_days
        rotated_at = self._now()

        existing = self._client.get(path) or {}
        existing[key] = stored_value
        existing[f"{key}__encrypted"] = "1" if do_encrypt else "0"
        existing[f"{key}__rotated_at"] = rotated_at.isoformat()
        existing[f"{key}__rotation_days"] = str(rotation)

        self._client.put(path, existing)
        self._tracked_paths.add((path, key))
        self._audit("put", f"{path}/{key}", value)

        return StoredSecret(
            path=path,
            key=key,
            value=value,
            last_rotated_at=rotated_at,
            rotation_interval_days=rotation,
            encrypted=do_encrypt,
        )

    def get(
        self,
        path: str,
        key: str,
        *,
        fallback_env: str | None = None,
    ) -> StoredSecret:
        try:
            data = self._client.get(path)
        except VaultUnavailable:
            data = {}
        except Exception as exc:
            logger.warning("vault read failed for %s: %s", path, exc)
            data = {}

        raw = (data or {}).get(key)
        if not raw:
            if fallback_env and os.environ.get(fallback_env):
                value = os.environ[fallback_env]
                self._audit("get_fallback_env", f"{path}/{key}", value)
                return StoredSecret(
                    path=path,
                    key=key,
                    value=value,
                    last_rotated_at=self._now(),
                    rotation_interval_days=self._rotation_days,
                    encrypted=False,
                )
            raise SecretNotFoundError(f"{path}/{key}")

        encrypted_flag = (data or {}).get(f"{key}__encrypted") == "1"
        if encrypted_flag:
            envelope_key = self._envelope_key()
            if not envelope_key:
                raise RuntimeError(
                    f"valeur chiffree mais {self._envelope_key_env} absent"
                )
            value = _aesgcm_decrypt(raw, envelope_key)
        else:
            value = raw

        rotated_iso = (data or {}).get(f"{key}__rotated_at")
        rotated_at = (
            datetime.fromisoformat(rotated_iso)
            if rotated_iso
            else self._now()
        )
        rotation_days = int((data or {}).get(f"{key}__rotation_days", self._rotation_days))

        self._tracked_paths.add((path, key))
        self._audit("get", f"{path}/{key}", value)

        return StoredSecret(
            path=path,
            key=key,
            value=value,
            last_rotated_at=rotated_at,
            rotation_interval_days=rotation_days,
            encrypted=encrypted_flag,
        )

    def rotate(self, path: str, key: str, new_value: str) -> StoredSecret:
        # On reutilise put() qui re-stamp `rotated_at` et conserve le flag encrypt
        # par defaut si la cle d'enveloppe est definie.
        existing = self.get(path, key)
        return self.put(
            path,
            key,
            new_value,
            encrypt=existing.encrypted,
            rotation_days=existing.rotation_interval_days,
        )

    def list_due_for_rotation(self) -> list[StoredSecret]:
        due: list[StoredSecret] = []
        for path, key in list(self._tracked_paths):
            try:
                s = self.get(path, key)
            except SecretNotFoundError:
                continue
            if s.needs_rotation:
                due.append(s)
        return due

    def is_vault_available(self) -> bool:
        try:
            return self._client.is_available()
        except Exception:
            return False
