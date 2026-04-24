"""XAI lightweight V5.8 : features importance + counterfactuals.

Pas de SHAP/LIME lib lourde. Implementation pure Python :
  1. Perturbation : pour chaque champ input, on perturbe (delete/flip/tweak)
     et on mesure la difference d'output -> feature importance.
  2. Counterfactuals : "Si X = Y, quel serait le resultat ?"
     Genere 2-3 what-if via petites modifications.
  3. Ahmed-friendly summary : texte court explicatif.

Integration :
    explainer = DecisionExplainer(pool, rules_engine)
    exp = await explainer.explain(decision_id, domain_id, input_ctx, output)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import asyncpg

logger = logging.getLogger("uba.intelligence.explainer")


@dataclass
class FeatureImportance:
    feature: str
    baseline_value: Any
    importance: float  # 0..1
    changed_output: bool
    impact_direction: str  # positive | negative | neutral

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "baseline_value": self.baseline_value,
            "importance": round(self.importance, 3),
            "changed_output": self.changed_output,
            "impact_direction": self.impact_direction,
        }


@dataclass
class Counterfactual:
    description: str
    perturbation: dict[str, Any]
    alternative_output: dict[str, Any]
    delta_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "perturbation": self.perturbation,
            "alternative_output": self.alternative_output,
            "delta_keys": self.delta_keys,
        }


class DecisionExplainer:
    """Genere explications + counterfactuals pour une decision."""

    def __init__(
        self, pool: asyncpg.Pool, rules_engine: Any | None = None,
    ) -> None:
        self.pool = pool
        self.rules_engine = rules_engine  # RulesEngine optionnel

    async def explain(
        self,
        decision_id: str | None,
        domain_id: str,
        operation: str,
        input_context: dict[str, Any],
        output: dict[str, Any],
    ) -> dict[str, Any]:
        """Genere explication complete + persiste."""
        start = time.perf_counter()
        dec_id = decision_id or str(uuid4())

        features = self._compute_feature_importance(
            domain_id, input_context, output,
        )
        counterfactuals = self._generate_counterfactuals(
            domain_id, input_context, output,
        )
        summary = self._generate_ahmed_summary(
            domain_id, operation, output, features, counterfactuals,
        )
        computation_ms = int((time.perf_counter() - start) * 1000)

        # Persiste (idempotent via PK)
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO decisions_explanations
                    (decision_id, domain_id, operation, input_context, output,
                     features_importance, counterfactuals, ahmed_summary,
                     method, computation_ms)
                VALUES ($1::uuid, $2, $3, $4::jsonb, $5::jsonb,
                        $6::jsonb, $7::jsonb, $8, 'perturbation', $9)
                ON CONFLICT (decision_id) DO UPDATE SET
                    features_importance = EXCLUDED.features_importance,
                    counterfactuals = EXCLUDED.counterfactuals,
                    ahmed_summary = EXCLUDED.ahmed_summary,
                    generated_at = NOW(),
                    computation_ms = EXCLUDED.computation_ms
                """,
                UUID(dec_id), domain_id, operation,
                json.dumps(input_context), json.dumps(output),
                json.dumps([f.to_dict() for f in features]),
                json.dumps([c.to_dict() for c in counterfactuals]),
                summary, computation_ms,
            )

        return {
            "decision_id": dec_id,
            "domain_id": domain_id,
            "operation": operation,
            "features_importance": [f.to_dict() for f in features],
            "counterfactuals": [c.to_dict() for c in counterfactuals],
            "ahmed_summary": summary,
            "computation_ms": computation_ms,
        }

    def _compute_feature_importance(
        self, domain_id: str, input_ctx: dict[str, Any], output: dict[str, Any],
    ) -> list[FeatureImportance]:
        """Perturbation-based : delete each feature, measure output diff."""
        features: list[FeatureImportance] = []
        if self.rules_engine is None:
            # Fallback sans rules_engine : features = cles input
            for k, v in input_ctx.items():
                features.append(FeatureImportance(
                    feature=k, baseline_value=v,
                    importance=0.5,
                    changed_output=False,
                    impact_direction="neutral",
                ))
            return features

        baseline_output = self.rules_engine.evaluate(
            domain_id, {"input": input_ctx},
        )
        baseline_output.pop("_rules_applied", None)

        for key, value in input_ctx.items():
            # Perturb : delete field
            perturbed_ctx = {k: v for k, v in input_ctx.items() if k != key}
            try:
                alt_output = self.rules_engine.evaluate(
                    domain_id, {"input": perturbed_ctx},
                )
                alt_output.pop("_rules_applied", None)
            except Exception:
                alt_output = {}

            diff_keys = _dict_diff_keys(baseline_output, alt_output)
            importance = min(1.0, len(diff_keys) / max(1, len(baseline_output)))
            direction = "neutral"
            if diff_keys:
                direction = _impact_direction(baseline_output, alt_output)
            features.append(FeatureImportance(
                feature=key, baseline_value=value, importance=importance,
                changed_output=bool(diff_keys), impact_direction=direction,
            ))

        # Sort : plus important d'abord
        features.sort(key=lambda f: -f.importance)
        return features

    def _generate_counterfactuals(
        self, domain_id: str, input_ctx: dict[str, Any],
        output: dict[str, Any],
    ) -> list[Counterfactual]:
        """3 counterfactuals via perturbations typiques."""
        if self.rules_engine is None:
            return []
        cfs: list[Counterfactual] = []
        for perturbation in _typical_perturbations(input_ctx):
            desc = perturbation.pop("__description__", "perturbation")
            alt_ctx = {**input_ctx, **perturbation}
            try:
                alt_out = self.rules_engine.evaluate(
                    domain_id, {"input": alt_ctx},
                )
                alt_out.pop("_rules_applied", None)
            except Exception:
                continue
            delta = _dict_diff_keys(output, alt_out)
            if delta:
                cfs.append(Counterfactual(
                    description=desc,
                    perturbation=perturbation,
                    alternative_output=alt_out,
                    delta_keys=delta,
                ))
            if len(cfs) >= 3:
                break
        return cfs

    def _generate_ahmed_summary(
        self, domain_id: str, operation: str, output: dict[str, Any],
        features: list[FeatureImportance],
        counterfactuals: list[Counterfactual],
    ) -> str:
        """Resume Ahmed-friendly en francais (2-3 phrases)."""
        top = [f for f in features if f.changed_output][:3]
        parts = [
            f"Le domaine {domain_id} a applique l'operation {operation}."
        ]
        if top:
            feature_names = ", ".join(f.feature for f in top)
            parts.append(f"Facteurs determinants : {feature_names}.")
        if counterfactuals:
            cf = counterfactuals[0]
            parts.append(f"What-if : {cf.description} -> sortie modifiee.")
        return " ".join(parts)

    async def get_cached(self, decision_id: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT decision_id, domain_id, operation, input_context,
                       output, features_importance, counterfactuals,
                       ahmed_summary, method, generated_at, computation_ms
                FROM decisions_explanations
                WHERE decision_id = $1::uuid
                """, UUID(decision_id),
            )
        if row is None:
            return None
        return {
            "decision_id": str(row["decision_id"]),
            "domain_id": row["domain_id"],
            "operation": row["operation"],
            "input_context": _json(row["input_context"]),
            "output": _json(row["output"]),
            "features_importance": _json(row["features_importance"]),
            "counterfactuals": _json(row["counterfactuals"]),
            "ahmed_summary": row["ahmed_summary"],
            "method": row["method"],
            "generated_at": row["generated_at"].isoformat(),
            "computation_ms": int(row["computation_ms"] or 0),
        }


# -------------------- helpers --------------------

def _dict_diff_keys(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    keys = set(a.keys()) | set(b.keys())
    return sorted(k for k in keys if a.get(k) != b.get(k))


def _impact_direction(a: dict[str, Any], b: dict[str, Any]) -> str:
    a_num = sum(v for v in a.values() if isinstance(v, (int, float)))
    b_num = sum(v for v in b.values() if isinstance(v, (int, float)))
    if a_num > b_num:
        return "positive"
    if a_num < b_num:
        return "negative"
    return "neutral"


def _typical_perturbations(input_ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Genere quelques perturbations representatives."""
    perts = []
    for key, value in list(input_ctx.items())[:5]:
        if isinstance(value, (int, float)):
            perts.append({
                "__description__": f"{key} divise par 2",
                key: value / 2 if value else 1,
            })
            perts.append({
                "__description__": f"{key} multiplie par 2",
                key: value * 2,
            })
        elif isinstance(value, bool):
            perts.append({
                "__description__": f"{key} inverse",
                key: not value,
            })
        elif isinstance(value, str):
            perts.append({
                "__description__": f"{key} vide",
                key: "",
            })
    return perts


def _json(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw
