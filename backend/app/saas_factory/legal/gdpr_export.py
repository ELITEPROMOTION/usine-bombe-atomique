"""GDPRExporter : Article 20 (right to data portability).

Collecte TOUTES les donnees liees a un projet client + son owner_email :
- projects (1 row)
- client_onboarding_sessions (FK)
- intelligence_qualifications + pricings + assemblies + project_progression
- handoff_requests
- payments + invoices + refunds
- hostinger_resources + ssl_certificates + backups (technique)
- ai_decisions_log (mais SANS prompt brut — juste hash + preview tronque,
  pour preserver les secrets ET respecter privacy)
- user_consents

Format : dict structurise serialisable JSON. Le caller (admin endpoint)
peut servir un fichier .json telechargeable.

⚠ Ce module ne touche PAS aux audit_events / evidence_ledger / mandates :
ces tables sont retenues pour obligation legale (Art 17§3) et ne
contiennent que des hashs/preuves, pas de PII directe.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GDPRExportPackage:
    project_id: UUID
    owner_email: str
    exported_at: datetime
    data: dict[str, Any]                  # JSON-ready
    record_counts: dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "project_id": str(self.project_id),
                "owner_email": self.owner_email,
                "exported_at": self.exported_at.isoformat(),
                "format_version": "1.0",
                "record_counts": self.record_counts,
                "data": self.data,
            },
            sort_keys=True, ensure_ascii=False, default=str, indent=2,
        )


# Tables a interroger : (table, query_template, count_key)
_EXPORT_QUERIES: tuple[tuple[str, str], ...] = (
    ("project", """
        SELECT project_id, owner_email, company_name, country, locale,
               currency, pack_id_hint, title, status, summary_json,
               created_at, updated_at, archived_at
          FROM projects
         WHERE project_id = $1
    """),
    ("onboarding_sessions", """
        SELECT session_id, current_step, completed_steps,
               partial_data_json, status, started_at, submitted_at
          FROM client_onboarding_sessions
         WHERE project_id = $1
    """),
    ("qualifications", """
        SELECT qualification_id, pack_hint, facets_json, detected_domain,
               detected_locales, risks, confidence, rationale, cdc_text_hash,
               created_at
          FROM intelligence_qualifications
         WHERE project_id = $1
         ORDER BY created_at DESC
    """),
    ("pricings", """
        SELECT pricing_id, pack_id, status, currency, net_price,
               tax_amount, gross_price, breakdown_json, created_at
          FROM intelligence_pricings
         WHERE project_id = $1
         ORDER BY created_at DESC
    """),
    ("assemblies", """
        SELECT assembly_id, pack_id, outcome, modules, deliverables,
               selected_addons, phase_weights_json, notes_json, created_at
          FROM intelligence_assemblies
         WHERE project_id = $1
         ORDER BY created_at DESC
    """),
    ("progression", """
        SELECT phase, weight_pct, status, completion_pct,
               started_at, completed_at, paywall_triggered_at, updated_at
          FROM project_progression
         WHERE project_id = $1
         ORDER BY phase
    """),
    ("handoff_requests", """
        SELECT handoff_id, action_type, state, target_email, locale,
               title, body, cta_url, expires_at, resolved_at, created_at
          FROM handoff_requests
         WHERE project_id = $1
         ORDER BY created_at DESC
    """),
    ("payments", """
        SELECT payment_id, amount_cents, currency, status, owner_email,
               country, locale, created_at, paid_at
          FROM payments
         WHERE project_id = $1
         ORDER BY created_at DESC
    """),
    ("invoices", """
        SELECT invoice_id, invoice_number, owner_email, country, locale,
               description, net_amount_cents, vat_pct, vat_amount_cents,
               gross_amount_cents, currency, vat_label, issued_at
          FROM invoices
         WHERE project_id = $1
         ORDER BY issued_at DESC
    """),
    ("hostinger_resources", """
        SELECT resource_id, resource_type, hostinger_id, status,
               metadata_json, created_at, updated_at
          FROM hostinger_resources
         WHERE project_id = $1
         ORDER BY created_at DESC
    """),
    ("ssl_certificates", """
        SELECT cert_id, domain, status, issued_at, expires_at,
               last_renewed_at, created_at
          FROM ssl_certificates
         WHERE project_id = $1
         ORDER BY issued_at DESC NULLS LAST
    """),
    ("backups", """
        SELECT backup_id, status, size_bytes, started_at, completed_at,
               hostinger_backup_id
          FROM backups
         WHERE project_id = $1
         ORDER BY started_at DESC
    """),
    ("ai_decisions_summary", """
        SELECT requested_provider, actual_provider, status,
               COUNT(*)::INT AS calls,
               SUM(tokens_in)::BIGINT AS tokens_in_total,
               SUM(tokens_out)::BIGINT AS tokens_out_total
          FROM ai_decisions_log
         WHERE project_id = $1
         GROUP BY requested_provider, actual_provider, status
    """),
)


def _serialize_value(v: Any) -> Any:
    """Convertit un Record / asyncpg-native pour JSON."""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    if isinstance(v, list):
        return [_serialize_value(x) for x in v]
    if isinstance(v, dict):
        return {k: _serialize_value(x) for k, x in v.items()}
    if isinstance(v, str):
        try:
            # asyncpg parfois retourne JSONB en string
            parsed = json.loads(v)
            return parsed if isinstance(parsed, dict | list) else v
        except (json.JSONDecodeError, ValueError):
            return v
    return v


class GDPRExporter:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def export_for_project(
        self, project_id: UUID,
    ) -> GDPRExportPackage:
        """Collecte toutes les donnees liees au projet. Echoue si
        projet introuvable.
        """
        async with self._pool.acquire() as conn:
            project_row = await conn.fetchrow(
                "SELECT owner_email FROM projects WHERE project_id = $1",
                project_id,
            )
            if project_row is None:
                raise LookupError(f"project {project_id} introuvable")
            owner_email = project_row["owner_email"]

            data: dict[str, Any] = {}
            counts: dict[str, int] = {}
            for key, query in _EXPORT_QUERIES:
                rows = await conn.fetch(query, project_id)
                serialized = [
                    {col: _serialize_value(val) for col, val in dict(r).items()}
                    for r in rows
                ]
                data[key] = serialized
                counts[key] = len(serialized)

            # Consents (par owner_email, pas project_id)
            consent_rows = await conn.fetch(
                """
                SELECT consent_id, scope, doc_version,
                       accepted_at, revoked_at
                  FROM user_consents
                 WHERE owner_email = $1
                 ORDER BY accepted_at DESC
                """,
                owner_email.lower(),
            )
            data["consents"] = [
                {col: _serialize_value(val) for col, val in dict(r).items()}
                for r in consent_rows
            ]
            counts["consents"] = len(consent_rows)

        logger.info(
            "gdpr.export project=%s owner=%s tables=%d records=%d",
            project_id, owner_email, len(counts), sum(counts.values()),
        )
        return GDPRExportPackage(
            project_id=project_id,
            owner_email=owner_email,
            exported_at=datetime.now(UTC),
            data=data,
            record_counts=counts,
        )
