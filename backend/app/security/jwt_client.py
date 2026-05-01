"""JWT client auth pour l'espace client (`/client/*`).

Pattern parallele a `jwt_admin.py` mais :
- Secret distinct (`JWT_CLIENT_SECRET`) pour eviter qu'un token client
  vole ne donne access aux endpoints admin.
- Issuer distinct (`uba-studio/client`) pour rejeter cross-issuer.
- Claims supplementaires : `project_id` (UUID, scope-bound auth) +
  `email` (display only).
- Pas de role : un client est un client. Tout endpoint `/client/*`
  exige juste un token client valide pour le project demande.

Cf. ADR-33 — JWT client claim project_id.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import UUID

from jose import JWTError, jwt

logger = logging.getLogger(__name__)


JWT_CLIENT_SECRET_ENV: Final[str] = "JWT_CLIENT_SECRET"
JWT_ALGORITHM: Final[str] = "HS256"
DEFAULT_TOKEN_TTL_MINUTES: Final[int] = 60 * 24       # 24h
ISSUER: Final[str] = "uba-studio/client"


class JWTClientError(RuntimeError):
    """Erreur generique JWT client (config absente, token invalide, etc.)."""


class JWTClientConfigMissingError(JWTClientError):
    """JWT_CLIENT_SECRET non configure."""


@dataclass(frozen=True)
class JWTClientPayload:
    sub: str             # owner_email
    project_id: UUID
    iat: int
    exp: int
    iss: str = ISSUER

    def to_claims(self) -> dict[str, Any]:
        return {
            "sub": self.sub,
            "project_id": str(self.project_id),
            "iat": self.iat,
            "exp": self.exp,
            "iss": self.iss,
        }


def _secret_or_raise() -> str:
    secret = os.environ.get(JWT_CLIENT_SECRET_ENV, "").strip()
    if not secret:
        raise JWTClientConfigMissingError(
            f"{JWT_CLIENT_SECRET_ENV} non configure",
        )
    if len(secret) < 32:
        raise JWTClientError(
            f"{JWT_CLIENT_SECRET_ENV} trop court (min 32 chars)",
        )
    return secret


def is_jwt_client_mode_enabled() -> bool:
    """True si JWT_CLIENT_SECRET est configure (>= 32 chars)."""
    secret = os.environ.get(JWT_CLIENT_SECRET_ENV, "").strip()
    return bool(secret) and len(secret) >= 32


def create_client_token(
    *,
    owner_email: str,
    project_id: UUID,
    ttl_minutes: int = DEFAULT_TOKEN_TTL_MINUTES,
) -> str:
    """Cree un JWT client signe HS256."""
    if not owner_email or "@" not in owner_email or len(owner_email) > 255:
        raise ValueError("owner_email invalide")
    if ttl_minutes < 1 or ttl_minutes > 30 * 24 * 60:
        raise ValueError("ttl_minutes doit etre dans [1..43200]")
    secret = _secret_or_raise()
    now = datetime.now(UTC)
    payload = JWTClientPayload(
        sub=owner_email.lower(),
        project_id=project_id,
        iat=int(now.timestamp()),
        exp=int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    )
    return jwt.encode(payload.to_claims(), secret, algorithm=JWT_ALGORITHM)


def verify_client_token(token: str) -> JWTClientPayload:
    """Verifie le token et retourne la payload. Leve `JWTClientError`."""
    if not token:
        raise JWTClientError("token vide")
    secret = _secret_or_raise()
    try:
        claims = jwt.decode(
            token, secret, algorithms=[JWT_ALGORITHM],
            issuer=ISSUER,
        )
    except JWTError as exc:
        raise JWTClientError(f"token invalide: {exc}") from exc

    sub = claims.get("sub")
    project_id_raw = claims.get("project_id")
    if not sub or not project_id_raw:
        raise JWTClientError("payload incomplete (sub/project_id manquant)")
    try:
        project_id = UUID(str(project_id_raw))
    except ValueError as exc:
        raise JWTClientError(
            f"project_id invalide: {project_id_raw!r}",
        ) from exc

    return JWTClientPayload(
        sub=str(sub),
        project_id=project_id,
        iat=int(claims.get("iat", 0)),
        exp=int(claims.get("exp", 0)),
        iss=str(claims.get("iss", ISSUER)),
    )
