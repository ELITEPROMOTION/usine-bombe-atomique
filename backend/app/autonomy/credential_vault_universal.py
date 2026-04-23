"""V5.1 BLOC 3 - Credential Vault Universal.

Avant toute demande A (compte/credentials), on interroge Vault :
  - secret/uba/credentials/<service>  -> email/password/token existants ?
Si present et frais, on REUTILISE au lieu de demander a Ahmed.

Schema stocke par service (KV v2 data field):
  {
    "email": "...", "password": "...", "token": "...",
    "created_at": "ISO", "last_used_at": "ISO",
    "ttl_days": 365, "is_oauth": false
  }
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.integrations.vault_client import VaultClient, VaultUnavailable

logger = logging.getLogger(__name__)


def _path(service: str) -> str:
    slug = service.lower().replace(" ", "_").replace("/", "_")
    return f"credentials/{slug}"


def lookup(service: str) -> dict[str, Any] | None:
    """Retourne le credential depuis Vault ou None."""
    try:
        vc = VaultClient()
        data = vc.get(_path(service))
    except VaultUnavailable:
        return None
    except Exception as exc:
        logger.debug("vault lookup %s failed: %s", service, exc)
        return None
    if not data:
        return None
    # Check TTL si present
    created = data.get("created_at")
    ttl = int(data.get("ttl_days", 0) or 0)
    if created and ttl:
        try:
            dt = datetime.fromisoformat(created)
            age_days = (datetime.now(timezone.utc) - dt).days
            if age_days > ttl:
                logger.info("credential %s expired (%dd > ttl %d)",
                            service, age_days, ttl)
                return None
        except ValueError:
            logger.debug("credential %s : created_at invalide, TTL ignore",
                         service)
    return data


def store(service: str, data: dict[str, Any], ttl_days: int = 365) -> bool:
    try:
        vc = VaultClient()
        payload = {
            **data,
            "created_at": data.get("created_at")
                           or datetime.now(timezone.utc).isoformat(),
            "ttl_days": ttl_days,
        }
        vc.put(_path(service), payload)
        return True
    except Exception as exc:
        logger.warning("vault store %s failed: %s", service, exc)
        return False


def mark_used(service: str) -> None:
    existing = lookup(service)
    if not existing:
        return
    existing["last_used_at"] = datetime.now(timezone.utc).isoformat()
    store(service, existing, ttl_days=int(existing.get("ttl_days", 365)))


def has_credential(service: str) -> bool:
    return lookup(service) is not None
