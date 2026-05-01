"""Helpers pour enrichir les events Sentry avec contexte V9.

**No-op gracieux** si `sentry_sdk` n'est pas installe ou pas initialise.
Les call-sites peuvent invoquer ces helpers sans tester explicitement
la presence du SDK.

Privacy : aucune PII brute n'est envoyee a Sentry. owner_email est
hashe SHA-256 avant tagging. Cf. ADR-28.
"""
from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def _hash_email(email: str) -> str:
    """Hash SHA-256 d'un email pour Sentry tagging (privacy GDPR)."""
    return hashlib.sha256(email.lower().encode("utf-8")).hexdigest()[:16]


@lru_cache(maxsize=1)
def _sentry_sdk_importable() -> bool:
    """Cache l'import — l'absence du SDK ne change pas runtime."""
    try:
        import sentry_sdk  # noqa: F401
    except ImportError:
        return False
    return True


def is_sentry_available() -> bool:
    """True si sentry_sdk est importable ET un client est initialise."""
    if not _sentry_sdk_importable():
        return False
    try:
        import sentry_sdk
        hub = sentry_sdk.Hub.current
        return hub.client is not None
    except (AttributeError, RuntimeError):
        return False


def _reset_sentry_cache_for_test() -> None:
    """Test helper — flush le lru_cache."""
    _sentry_sdk_importable.cache_clear()


def add_project_context(
    project_id: UUID | str,
    *,
    owner_email: str | None = None,
    pack_id: str | None = None,
    status: str | None = None,
) -> bool:
    """Ajoute le contexte projet au scope Sentry courant.

    Retourne True si l'enrichissement a ete applique, False si Sentry
    n'est pas disponible (no-op silencieux).
    """
    if not is_sentry_available():
        return False
    try:
        import sentry_sdk
        with sentry_sdk.configure_scope() as scope:
            scope.set_tag("project_id", str(project_id))
            if pack_id:
                scope.set_tag("pack_id", pack_id)
            if status:
                scope.set_tag("project_status", status)
            if owner_email:
                # email hashe — pas de PII brute
                scope.set_user({"id": _hash_email(owner_email)})
        return True
    except Exception as exc:
        logger.debug("sentry add_project_context failed: %s", exc)
        return False


def add_payment_context(
    payment_id: UUID | str,
    *,
    amount_cents: int | None = None,
    currency: str | None = None,
    status: str | None = None,
    auth_mode: str | None = None,
) -> bool:
    """Ajoute le contexte paiement au scope Sentry."""
    if not is_sentry_available():
        return False
    try:
        import sentry_sdk
        with sentry_sdk.configure_scope() as scope:
            scope.set_tag("payment_id", str(payment_id))
            ctx: dict[str, Any] = {}
            if amount_cents is not None:
                ctx["amount_cents"] = amount_cents
            if currency:
                ctx["currency"] = currency
            if status:
                ctx["status"] = status
                scope.set_tag("payment_status", status)
            if auth_mode:
                scope.set_tag("auth_mode", auth_mode)
            if ctx:
                scope.set_context("payment", ctx)
        return True
    except Exception as exc:
        logger.debug("sentry add_payment_context failed: %s", exc)
        return False


def capture_v9_exception(
    exc: BaseException,
    *,
    project_id: UUID | str | None = None,
    extra: dict[str, Any] | None = None,
) -> bool:
    """Envoie une exception a Sentry avec contexte V9 enrichi."""
    if not is_sentry_available():
        return False
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if project_id is not None:
                scope.set_tag("project_id", str(project_id))
            if extra:
                for k, v in extra.items():
                    scope.set_extra(k, v)
            sentry_sdk.capture_exception(exc)
        return True
    except Exception as fail:
        logger.debug("sentry capture_v9_exception failed: %s", fail)
        return False
