"""JWT-based admin auth + RBAC.

Replace progressivement le `X-Admin-Token` stopgap de 9N par un JWT signe
HS256 avec un role embarque (`admin`, `viewer`, `auditor`).

- `admin`   : full access (override, mutations)
- `viewer`  : lecture seule (dashboards, listes)
- `auditor` : lecture + admin_actions, mais pas de mutations

Le JWT est signe avec `JWT_ADMIN_SECRET` env var. Si non configuree,
le moteur retombe sur le mode token legacy 9N (cf. dependencies.py).
"""
from __future__ import annotations

import enum
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from jose import JWTError, jwt

logger = logging.getLogger(__name__)


JWT_ADMIN_SECRET_ENV: Final[str] = "JWT_ADMIN_SECRET"
JWT_ALGORITHM: Final[str] = "HS256"
DEFAULT_TOKEN_TTL_MINUTES: Final[int] = 60
ISSUER: Final[str] = "uba-studio/admin"


class AdminRole(str, enum.Enum):
    ADMIN = "admin"        # mutations + override
    VIEWER = "viewer"      # lecture dashboards
    AUDITOR = "auditor"    # lecture + admin_actions, pas de mutations


# Permissions par role (extensible)
_ROLE_PERMISSIONS: dict[AdminRole, frozenset[str]] = {
    AdminRole.ADMIN: frozenset({"read", "write", "override", "audit"}),
    AdminRole.VIEWER: frozenset({"read"}),
    AdminRole.AUDITOR: frozenset({"read", "audit"}),
}


class JWTAdminError(RuntimeError):
    """Erreur generique JWT admin (config absente, token invalide, etc.)."""


class JWTConfigMissingError(JWTAdminError):
    """JWT_ADMIN_SECRET non configure — passer en mode legacy."""


@dataclass(frozen=True)
class JWTPayload:
    sub: str            # admin_id (e.g. 'ahmed')
    role: AdminRole
    iat: int
    exp: int
    iss: str = ISSUER

    def to_claims(self) -> dict[str, Any]:
        return {
            "sub": self.sub,
            "role": self.role.value,
            "iat": self.iat,
            "exp": self.exp,
            "iss": self.iss,
        }


def _secret_or_raise() -> str:
    secret = os.environ.get(JWT_ADMIN_SECRET_ENV, "").strip()
    if not secret:
        raise JWTConfigMissingError(
            f"{JWT_ADMIN_SECRET_ENV} non configure"
        )
    if len(secret) < 32:
        raise JWTAdminError(
            f"{JWT_ADMIN_SECRET_ENV} trop court (min 32 chars)"
        )
    return secret


def is_jwt_mode_enabled() -> bool:
    """True si JWT_ADMIN_SECRET est configure (>= 32 chars)."""
    secret = os.environ.get(JWT_ADMIN_SECRET_ENV, "").strip()
    return bool(secret) and len(secret) >= 32


def create_admin_token(
    *,
    admin_id: str,
    role: AdminRole,
    ttl_minutes: int = DEFAULT_TOKEN_TTL_MINUTES,
) -> str:
    """Cree un JWT signe HS256."""
    if not admin_id or len(admin_id) > 80:
        raise ValueError("admin_id requis, max 80 chars")
    if ttl_minutes < 1 or ttl_minutes > 24 * 60:
        raise ValueError("ttl_minutes doit etre dans [1..1440]")
    secret = _secret_or_raise()
    now = datetime.now(UTC)
    payload = JWTPayload(
        sub=admin_id, role=role,
        iat=int(now.timestamp()),
        exp=int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    )
    return jwt.encode(payload.to_claims(), secret, algorithm=JWT_ALGORITHM)


def verify_admin_token(token: str) -> JWTPayload:
    """Verifie le token et retourne la payload. Leve `JWTAdminError` si invalide."""
    if not token:
        raise JWTAdminError("token vide")
    secret = _secret_or_raise()
    try:
        claims = jwt.decode(
            token, secret, algorithms=[JWT_ALGORITHM],
            issuer=ISSUER,
        )
    except JWTError as exc:
        raise JWTAdminError(f"token invalide: {exc}") from exc

    sub = claims.get("sub")
    role_raw = claims.get("role")
    if not sub or not role_raw:
        raise JWTAdminError("payload incomplete (sub/role manquant)")
    try:
        role = AdminRole(role_raw)
    except ValueError as exc:
        raise JWTAdminError(f"role inconnu: {role_raw!r}") from exc

    return JWTPayload(
        sub=str(sub), role=role,
        iat=int(claims.get("iat", 0)),
        exp=int(claims.get("exp", 0)),
        iss=str(claims.get("iss", ISSUER)),
    )


def has_permission(role: AdminRole, permission: str) -> bool:
    return permission in _ROLE_PERMISSIONS.get(role, frozenset())


def require_permission(role: AdminRole, permission: str) -> None:
    """Leve `JWTAdminError` si le role n'a pas la permission demandee."""
    if not has_permission(role, permission):
        raise JWTAdminError(
            f"role {role.value!r} sans permission {permission!r}"
        )
