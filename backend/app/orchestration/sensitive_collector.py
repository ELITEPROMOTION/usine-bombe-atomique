"""Upgrade 16 (BLOC E) - Collecte sensible.

Distingue 3 categories d'informations :
1. AUTO           : deductibles par le systeme (hash, uuid, constantes DZ, ...)
2. TOOLS          : lisibles via les outils connectes (vault, tool_registry)
3. USER_REQUIRED  : exigent une saisie humaine (email, mot de passe,
                    paiement, OTP, captcha, carte, document officiel)

Pour la categorie USER_REQUIRED, on emet un FieldRequest via pending_user_inputs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from app.intake.field_collector import FieldRequest

CATEGORY_AUTO = "auto"
CATEGORY_TOOLS = "tools"
CATEGORY_USER = "user_required"


USER_REQUIRED_PATTERNS = (
    "carte bancaire", "credit card", "numero de carte", "cvv", "cvc",
    "paiement", "payment", "otp", "code a 6 chiffres", "captcha",
    "mot de passe", "password", "cle secrete perso", "cheque",
    "passeport", "piece d'identite", "signature manuscrite",
)

TOOLS_PATTERNS = (
    "cle api", "api key", "token", "secret", "bearer",
    "access_key", "client_id", "client_secret", "webhook secret",
)


@dataclass
class InfoNeed:
    label: str
    category: str       # auto | tools | user_required
    reason: str
    field_request: FieldRequest | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label, "category": self.category,
            "reason": self.reason,
            "field_request": self.field_request.to_dict() if self.field_request else None,
        }


def classify(label: str) -> str:
    low = label.lower()
    if any(p in low for p in USER_REQUIRED_PATTERNS):
        return CATEGORY_USER
    if any(p in low for p in TOOLS_PATTERNS):
        return CATEGORY_TOOLS
    return CATEGORY_AUTO


async def persist_request(
    pool: asyncpg.Pool, task_id: str, req: FieldRequest,
    tool_id: str | None = None,
) -> str:
    """Persiste un FieldRequest dans `pending_user_inputs` et renvoie son id."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO pending_user_inputs
              (task_id, tool_id, request_kind, fields, context)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            RETURNING id
            """,
            UUID(task_id), tool_id, req.request_kind,
            json.dumps([f.to_dict() for f in req.fields]),
            req.context,
        )
    return str(row["id"])


async def submit_response(
    pool: asyncpg.Pool, request_id: str, payload: dict[str, Any],
) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE pending_user_inputs
            SET submission_payload = $2::jsonb,
                status = 'submitted', submitted_at = NOW()
            WHERE id = $1 AND status = 'awaiting'
            RETURNING id
            """,
            UUID(request_id), json.dumps(payload),
        )
    return row is not None


async def list_awaiting(
    pool: asyncpg.Pool, task_id: str | None = None, limit: int = 50,
) -> list[dict[str, Any]]:
    sql = ("SELECT id, task_id, tool_id, request_kind, fields, context, "
           "created_at, expires_at "
           "FROM pending_user_inputs WHERE status = 'awaiting' "
           "AND expires_at > NOW()")
    args: list[Any] = []
    if task_id:
        sql += " AND task_id = $1"
        args.append(UUID(task_id))
    sql += f" ORDER BY created_at DESC LIMIT {int(limit)}"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    out: list[dict[str, Any]] = []
    for r in rows:
        fields = r["fields"]
        if isinstance(fields, str):
            fields = json.loads(fields)
        out.append({
            "id": str(r["id"]),
            "task_id": str(r["task_id"]) if r["task_id"] else None,
            "tool_id": r["tool_id"],
            "request_kind": r["request_kind"],
            "context": r["context"],
            "fields": fields,
            "created_at": r["created_at"].isoformat(),
            "expires_at": r["expires_at"].isoformat(),
        })
    return out
