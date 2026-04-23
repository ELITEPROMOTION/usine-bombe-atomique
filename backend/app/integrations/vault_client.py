"""Vault KV v2 client - secrets migres hors du .env.

En dev, Vault est lance en mode dev avec un token root (`VAULT_ROOT_TOKEN`).
En prod, AppRole ou K8s auth.

Path convention : `secret/uba/<section>/<key>` avec KV v2.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MOUNT = "secret"
_PREFIX = "uba"


class VaultUnavailable(RuntimeError):
    pass


class VaultClient:
    """Wrapper minimaliste autour de hvac avec cache et fallback env."""

    def __init__(self, addr: str | None = None, token: str | None = None) -> None:
        self.addr = addr or os.environ.get("VAULT_ADDR", "http://vault:8200")
        self.token = token or os.environ.get("VAULT_TOKEN", "uba-dev-root")
        self._hvac: Any | None = None
        self._cache: dict[str, dict[str, Any]] = {}

    def _client(self):
        if self._hvac is None:
            try:
                import hvac  # type: ignore
            except ImportError as exc:
                raise VaultUnavailable(f"hvac not installed: {exc}") from exc
            self._hvac = hvac.Client(url=self.addr, token=self.token)
        return self._hvac

    def is_available(self) -> bool:
        try:
            return bool(self._client().is_authenticated())
        except Exception as exc:
            logger.debug("vault unavailable: %s", exc)
            return False

    def put(self, path: str, data: dict[str, Any]) -> None:
        """Ecrit un secret au path `uba/<path>` dans le mount `secret`."""
        client = self._client()
        client.secrets.kv.v2.create_or_update_secret(
            mount_point=_DEFAULT_MOUNT,
            path=f"{_PREFIX}/{path}",
            secret=data,
        )
        self._cache.pop(path, None)
        logger.info("vault put uba/%s (%d keys)", path, len(data))

    def get(self, path: str, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
        """Lit un secret. Retourne `default` si absent ou vault indispo."""
        if path in self._cache:
            return self._cache[path]
        try:
            resp = self._client().secrets.kv.v2.read_secret_version(
                mount_point=_DEFAULT_MOUNT,
                path=f"{_PREFIX}/{path}",
                raise_on_deleted_version=False,
            )
            data = resp["data"]["data"]
            self._cache[path] = data
            return data
        except Exception as exc:
            logger.debug("vault read uba/%s failed: %s", path, exc)
            return default if default is not None else {}

    def get_key(self, path: str, key: str, fallback_env: str | None = None) -> str:
        """Retourne data[key] au path donne ; fallback sur variable d'env si miss."""
        data = self.get(path)
        if data.get(key):
            return str(data[key])
        if fallback_env and os.environ.get(fallback_env):
            return os.environ[fallback_env]
        return ""


@lru_cache
def get_vault() -> VaultClient:
    return VaultClient()


def seed_from_env(client: VaultClient) -> dict[str, bool]:
    """Migration : prend ce qu'il y a dans l'env et le pousse dans Vault.
    Retourne un dict {path: ecrit_ou_deja_present}.
    """
    if not client.is_available():
        raise VaultUnavailable("Vault unreachable for seed")
    seed_map = {
        "anthropic": {"api_key": os.environ.get("ANTHROPIC_API_KEY", "")},
        "postgres": {"password": os.environ.get("POSTGRES_PASSWORD", "")},
        "redis": {"password": os.environ.get("REDIS_PASSWORD", "")},
        "jwt": {"secret": os.environ.get("JWT_SECRET", "")},
        "sonarqube": {"token": os.environ.get("SONAR_TOKEN", "")},
    }
    out: dict[str, bool] = {}
    for path, data in seed_map.items():
        if any(v for v in data.values()):
            client.put(path, data)
            out[path] = True
        else:
            out[path] = False
    return out
