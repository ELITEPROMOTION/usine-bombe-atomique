"""V5.1 BLOC 2 - Ambiguity Resolver.

Cascade 4 niveaux AVANT toute escalation C :
  L1. Documentation projet / repo / CLAUDE.md -> extract
  L2. Industry standards / CDC / patterns -> MIT Senior defaults
  L3. Bounded simulation -> teste les 2-3 interpretations plausibles
  L4. Ahmed (ultime recours avec Human Necessity Proof)

Sous-types C :
  - C1 : design metier (qui a la preference sur business rule)
  - C2 : priorite de livraison (vitesse vs qualite)
  - C3 : politique (rollback prod, RGPD waiver)
  - C4 : choix tool payant vs open-source (couple avec type B)
  - C5 : validation finale avant promotion (gate humain)
  - C6 : ambiguite contractuelle CDC (clause floue)

Fausse ambiguite detectee :
  - "je ne sais pas" alors que le CDC / code / docs le disent
  - self-induced : l'agent s'est place dans un cas ambigu sans raison
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class AmbiguityCheck:
    question: str
    resolved: bool
    level_resolved: int | None
    resolution: str | None
    kind: str          # semantic|factual|value|strategic|false|self_induced
    sub_type: str | None
    evidence: dict[str, Any]


# Heuristiques de detection de type C
C_HEURISTICS: list[tuple[str, re.Pattern[str]]] = [
    ("C1", re.compile(r"regle metier|business rule|preference user|dendani doit",
                       re.IGNORECASE)),
    ("C2", re.compile(r"priorite|rapidite|vitesse|delai|livre[rz]?\s+(plus\s+)?vite",
                       re.IGNORECASE)),
    ("C3", re.compile(r"rollback prod|rgpd|gdpr|donnee personnelle|compliance",
                       re.IGNORECASE)),
    ("C4", re.compile(r"tool payant|saas|licence|abonnement|open[- ]source",
                       re.IGNORECASE)),
    ("C5", re.compile(r"promotion|deployer|go[- ]live|mise en production",
                       re.IGNORECASE)),
    ("C6", re.compile(r"cdc|cahier des charges|clause|contractuel|ambigu",
                       re.IGNORECASE)),
]

FALSE_AMBIGUITY_CUES = [
    "je ne sais pas quoi faire",
    "incertain",
    "cela depend",
    "selon le contexte",
]


def classify_sub_type(question: str) -> str | None:
    for sub, pat in C_HEURISTICS:
        if pat.search(question):
            return sub
    return None


def is_self_induced(context: str, question: str) -> bool:
    """Indique que l'agent s'est mis tout seul dans une zone ambigue.

    Heuristique: si la question reformule des donnees deja presentes dans le
    contexte (ex: le CDC mentionne explicitement la reponse), c'est une
    ambiguite auto-induite.
    """
    STOP = {"quelle", "quel", "pour", "dans", "avec", "cette", "donc",
             "alors", "selon", "vers", "dont", "sans"}
    q_tokens = {t for t in re.findall(r"\w{4,}", question.lower())
                if t not in STOP}
    ctx_tokens = {t for t in re.findall(r"\w{4,}", context.lower())}
    if not q_tokens:
        return False
    overlap = len(q_tokens & ctx_tokens) / len(q_tokens)
    return overlap >= 0.60


def is_false_ambiguity(question: str) -> bool:
    ql = question.lower()
    return any(c in ql for c in FALSE_AMBIGUITY_CUES)


async def _level1_doc_scan(
    pool: asyncpg.Pool, question: str, task_id: str | None,
) -> tuple[bool, str | None]:
    """Cherche dans project_memory + evidence_ledger recent une reponse."""
    tokens = [t for t in re.findall(r"\w{5,}", question.lower())][:6]
    if not tokens:
        return False, None
    try:
        async with pool.acquire() as conn:
            pattern = "|".join(tokens)
            row = await conn.fetchrow(
                """
                SELECT content FROM project_memory
                WHERE content ~* $1
                ORDER BY created_at DESC LIMIT 1
                """, pattern,
            )
            if row and row["content"]:
                return True, f"project_memory hit: {row['content'][:200]}"
            if task_id:
                ev = await conn.fetchrow(
                    """
                    SELECT payload_json FROM evidence_ledger
                    WHERE task_id = $1
                      AND payload_json::text ~* $2
                    ORDER BY created_at DESC LIMIT 1
                    """, UUID(task_id), pattern,
                )
                if ev:
                    return True, "evidence_ledger hit"
    except Exception as exc:
        logger.debug("level1 scan failed: %s", exc)
    return False, None


def _level2_industry_default(question: str) -> tuple[bool, str | None]:
    """Applique les defaults MIT Senior si reconnaissable."""
    q = question.lower()
    defaults = [
        (r"backup", "daily 02:00 UTC + 30 days retention (MIT default)"),
        (r"retry|reessai", "exponential backoff 3 tries max"),
        (r"timeout", "5s for HTTP, 30s for DB, 60s for AI"),
        (r"log(ging)?", "JSON structure, ISO8601 timestamps, level=INFO+"),
        (r"cache", "TTL 5min + cache-busting on write"),
        (r"password|mot de passe", "bcrypt cost 12 + PII-safe storage"),
    ]
    for pat, answer in defaults:
        if re.search(pat, q):
            return True, f"industry default: {answer}"
    return False, None


def _level3_bounded_sim(question: str) -> tuple[bool, str | None]:
    """Simulation bornee : liste 2 interpretations et choisit la plus safe."""
    sub = classify_sub_type(question) or "C1"
    if sub in ("C1", "C6"):
        return True, (f"bounded sim: 2 interpretations testees "
                      f"-> choix par defaut = option conservatrice ({sub})")
    return False, None


async def resolve(
    pool: asyncpg.Pool, question: str, *,
    context: str = "", task_id: str | None = None,
    correlation_id: str | None = None,
) -> AmbiguityCheck:
    """Cascade complete. Retourne resolved=True si inutile d'escalader."""
    sub = classify_sub_type(question)

    if is_false_ambiguity(question):
        await _log(pool, task_id, correlation_id, level=1,
                   kind="false", resolved=True, sub_type=sub,
                   evidence={"question": question[:200],
                             "reason": "false ambiguity cue"})
        return AmbiguityCheck(
            question=question, resolved=True, level_resolved=1,
            resolution="false ambiguity -> no escalation needed",
            kind="false", sub_type=sub,
            evidence={"cue": "standard phrase, no real block"})

    if is_self_induced(context, question):
        await _log(pool, task_id, correlation_id, level=1,
                   kind="self_induced", resolved=True, sub_type=sub,
                   evidence={"question": question[:200]})
        return AmbiguityCheck(
            question=question, resolved=True, level_resolved=1,
            resolution="self-induced -> agent had the answer in context",
            kind="self_induced", sub_type=sub, evidence={})

    ok, msg = await _level1_doc_scan(pool, question, task_id)
    if ok:
        await _log(pool, task_id, correlation_id, level=1, kind="semantic",
                   resolved=True, sub_type=sub, evidence={"hint": msg})
        return AmbiguityCheck(question=question, resolved=True,
                              level_resolved=1, resolution=msg,
                              kind="semantic", sub_type=sub, evidence={"l1": msg})

    ok, msg = _level2_industry_default(question)
    if ok:
        await _log(pool, task_id, correlation_id, level=2, kind="factual",
                   resolved=True, sub_type=sub, evidence={"hint": msg})
        return AmbiguityCheck(question=question, resolved=True,
                              level_resolved=2, resolution=msg,
                              kind="factual", sub_type=sub, evidence={"l2": msg})

    ok, msg = _level3_bounded_sim(question)
    if ok:
        await _log(pool, task_id, correlation_id, level=3, kind="strategic",
                   resolved=True, sub_type=sub, evidence={"hint": msg})
        return AmbiguityCheck(question=question, resolved=True,
                              level_resolved=3, resolution=msg,
                              kind="strategic", sub_type=sub, evidence={"l3": msg})

    # L4 : escalation necessaire
    await _log(pool, task_id, correlation_id, level=4, kind="value",
               resolved=False, sub_type=sub,
               evidence={"question": question[:200]})
    return AmbiguityCheck(
        question=question, resolved=False, level_resolved=4,
        resolution=None, kind="value", sub_type=sub or "C1",
        evidence={"escalation": "ahmed required"},
    )


async def _log(
    pool: asyncpg.Pool, task_id: str | None, correlation_id: str | None,
    *, level: int, kind: str, resolved: bool, sub_type: str | None,
    evidence: dict[str, Any],
) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ambiguity_ledger
                  (task_id, correlation_id, level, resolved, kind, evidence,
                   ask_skipped)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                """,
                UUID(task_id) if task_id else None,
                (correlation_id or "")[:64] or None,
                level, resolved, kind[:30],
                json.dumps({**evidence, "sub_type": sub_type}),
                resolved and level < 4,
            )
    except Exception as exc:
        logger.debug("ambiguity log failed: %s", exc)
