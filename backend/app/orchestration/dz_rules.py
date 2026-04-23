"""Upgrade 30 - Regles fiscales DZ parametrables via DB.

Les regles vivent dans `dz_rules_config` (versionnees). L'agent #18 lit
cette table plutot que d'avoir les patterns en dur. Les regles peuvent
etre ajoutees ou ajustees via un endpoint admin sans redeploiement.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class DZRule:
    rule_code: str
    version: int
    label: str
    regex_positive: str | None
    regex_negative: str | None
    severity: str


async def load_active(pool: asyncpg.Pool) -> list[DZRule]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT rule_code, version, label, regex_positive,
                   regex_negative, severity
            FROM dz_rules_config
            WHERE is_active = TRUE
            ORDER BY rule_code, version DESC
            """
        )
    # Garde la version max par rule_code
    by_code: dict[str, DZRule] = {}
    for r in rows:
        rule = DZRule(
            rule_code=r["rule_code"], version=r["version"], label=r["label"],
            regex_positive=r["regex_positive"], regex_negative=r["regex_negative"],
            severity=r["severity"],
        )
        if rule.rule_code not in by_code:
            by_code[rule.rule_code] = rule
    return sorted(by_code.values(), key=lambda x: x.rule_code)


def apply_rules(corpus: str, rules: list[DZRule]) -> list[dict[str, Any]]:
    """Retourne le verdict de chaque regle appliquee sur le corpus."""
    out: list[dict[str, Any]] = []
    for rule in rules:
        applicable = True
        matched = False
        if rule.regex_positive:
            try:
                matched = bool(re.search(rule.regex_positive, corpus, re.IGNORECASE))
            except re.error as exc:
                logger.warning("regex invalid for %s: %s", rule.rule_code, exc)
                continue
        if rule.regex_negative and re.search(rule.regex_negative, corpus, re.IGNORECASE):
            matched = False
        out.append({
            "rule_code": rule.rule_code,
            "version": rule.version,
            "label": rule.label,
            "applicable": applicable,
            "passed": matched,
            "severity": rule.severity,
        })
    return out


async def upsert_rule(
    pool: asyncpg.Pool, *,
    rule_code: str, label: str, regex_positive: str | None = None,
    regex_negative: str | None = None, severity: str = "medium",
    created_by: str = "admin",
) -> dict[str, Any]:
    """Insere une nouvelle version d'une regle (version auto-incrementee)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COALESCE(MAX(version), 0) AS maxv FROM dz_rules_config "
            "WHERE rule_code = $1", rule_code,
        )
        new_version = int(row["maxv"] or 0) + 1
        await conn.execute(
            """
            INSERT INTO dz_rules_config
              (rule_code, version, label, regex_positive, regex_negative,
               severity, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            rule_code, new_version, label, regex_positive, regex_negative,
            severity, created_by,
        )
    return {"rule_code": rule_code, "new_version": new_version}
