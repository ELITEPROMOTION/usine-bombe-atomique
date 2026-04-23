"""V5.1 BLOC 5 - Autonomy Simulation Lab.

Replay l'historique des interventions pour mesurer l'impact d'une policy
(ex: "si on baisse le seuil C de 0.40 a 0.30, combien d'escalations
devenaient autonomes, et combien auraient ete erreurs ?").

Entree : policy candidate (thresholds, rules)
Sortie : metriques simulees {avoidable_before, avoidable_after, risk_added}

Le lab ne modifie RIEN en prod. Il genere des propositions pour
self_improver, qui decide ou non de les appliquer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class Policy:
    escalate_confidence_threshold: float = 0.40
    constrain_confidence_threshold: float = 0.60
    probe_confidence_threshold: float = 0.75
    continue_confidence_threshold: float = 0.92


@dataclass
class SimResult:
    policy: dict[str, float]
    samples: int
    would_continue: int
    would_constrain: int
    would_probe: int
    would_defer: int
    would_escalate: int
    avoidable_escalations: int
    risky_continuations: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy": self.policy, "samples": self.samples,
            "mode_counts": {
                "CONTINUE": self.would_continue,
                "CONSTRAIN": self.would_constrain,
                "PROBE": self.would_probe,
                "DEFER": self.would_defer,
                "ESCALATE": self.would_escalate,
            },
            "avoidable_escalations": self.avoidable_escalations,
            "risky_continuations": self.risky_continuations,
        }


async def replay(
    pool: asyncpg.Pool, policy: Policy, window_days: int = 14,
) -> SimResult:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.form_type, p.c_sub_type, p.criticality,
                   o.was_necessary,
                   (e.payload->>'confidence')::float AS confidence
            FROM pending_user_inputs p
            LEFT JOIN intervention_outcomes o ON o.pending_request_id = p.id
            LEFT JOIN LATERAL (
              SELECT payload_json AS payload FROM evidence_ledger
              WHERE task_id = p.task_id AND kind = 'decision'
              ORDER BY created_at DESC LIMIT 1
            ) e ON TRUE
            WHERE p.created_at >= NOW() - INTERVAL '1 day' * $1
            LIMIT 2000
            """, window_days,
        )

    counts = {"CONTINUE": 0, "CONSTRAIN": 0, "PROBE": 0, "DEFER": 0, "ESCALATE": 0}
    avoidable = 0
    risky = 0
    n = 0
    for r in rows:
        conf = r["confidence"]
        if conf is None:
            # Si pas de score, on approxime par criticality
            conf = {"low": 0.85, "medium": 0.65, "high": 0.45,
                    "critical": 0.30}.get(r["criticality"] or "medium", 0.65)
        conf = float(conf)
        n += 1
        # Simule ladder
        if conf > policy.continue_confidence_threshold:
            mode = "CONTINUE"
        elif conf > policy.probe_confidence_threshold:
            mode = "PROBE"
        elif conf > policy.constrain_confidence_threshold:
            mode = "CONSTRAIN"
        elif conf > policy.escalate_confidence_threshold:
            mode = "DEFER"
        else:
            mode = "ESCALATE"
        counts[mode] += 1

        # La realite observee : etait-ce vraiment necessaire ?
        really_needed = bool(r["was_necessary"])
        if mode != "ESCALATE" and really_needed:
            risky += 1
        if mode == "ESCALATE" and not really_needed:
            avoidable += 1

    return SimResult(
        policy=policy.__dict__, samples=n,
        would_continue=counts["CONTINUE"],
        would_constrain=counts["CONSTRAIN"],
        would_probe=counts["PROBE"],
        would_defer=counts["DEFER"],
        would_escalate=counts["ESCALATE"],
        avoidable_escalations=avoidable,
        risky_continuations=risky,
    )


async def grid_search(
    pool: asyncpg.Pool, window_days: int = 14,
) -> dict[str, Any]:
    """Teste une petite grille de policies et retourne la meilleure."""
    best: dict[str, Any] | None = None
    results: list[dict[str, Any]] = []
    for esc_t in (0.30, 0.40, 0.50):
        for con_t in (0.55, 0.60, 0.65):
            if con_t <= esc_t:
                continue
            p = Policy(escalate_confidence_threshold=esc_t,
                        constrain_confidence_threshold=con_t)
            r = await replay(pool, p, window_days=window_days)
            score = (
                -r.avoidable_escalations * 1.0 +
                -r.risky_continuations * 3.0      # on penalise 3x les risques
            )
            d = {**r.to_dict(), "score": score}
            results.append(d)
            if best is None or score > best["score"]:
                best = d
    return {"best": best, "all": results}
