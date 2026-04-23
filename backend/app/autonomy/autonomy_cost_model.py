"""V5.1 BLOC 6 - Autonomy Cost Model.

Chaque decision a un cout compose :
  - API cost    : tokens Anthropic x prix tier
  - Latence cost: duration_ms * VALUE_PER_MS (ex: 0.0001 USD/ms)
  - Humain cost : si intervention Ahmed, mins * HOURLY_RATE/60
  - Risque cost : proba_failure * downstream_cost_if_failure

Usage : le governor choisit la mode qui MINIMISE la somme.
  - CONTINUE : peu de cout humain, risque = faible (si confiance haute)
  - ESCALATE : cout humain eleve, risque = nul
  - PROBE    : cout exec additionnel mais couvre l'incertitude
"""
from __future__ import annotations

from dataclasses import dataclass

# Constantes ajustables (seeded from dashboard_readiness data)
HOURLY_RATE_USD = 120.0          # cout horaire Ahmed (CEO)
VALUE_PER_MS = 0.0001            # cout par ms d'attente projet
CONFIDENCE_TO_RISK = {
    1.0: 0.01, 0.9: 0.05, 0.8: 0.10, 0.7: 0.18,
    0.6: 0.28, 0.5: 0.42, 0.4: 0.58, 0.3: 0.72,
    0.2: 0.85, 0.1: 0.95, 0.0: 1.0,
}


@dataclass
class CostBreakdown:
    api_usd: float
    latency_usd: float
    human_usd: float
    risk_usd: float
    total_usd: float

    def to_dict(self) -> dict[str, float]:
        return {
            "api_usd": round(self.api_usd, 4),
            "latency_usd": round(self.latency_usd, 4),
            "human_usd": round(self.human_usd, 4),
            "risk_usd": round(self.risk_usd, 4),
            "total_usd": round(self.total_usd, 4),
        }


def _risk_factor(confidence: float) -> float:
    c = max(0.0, min(1.0, confidence))
    # linear interpolation over 0..1 with step 0.1
    lo = round(c * 10) / 10
    return CONFIDENCE_TO_RISK.get(lo, 0.5)


def estimate(
    *, confidence: float, mode: str,
    tokens_in: int = 0, tokens_out: int = 0,
    duration_ms: int = 0,
    human_minutes: float = 0.0,
    downstream_cost_usd: float = 100.0,
) -> CostBreakdown:
    # Anthropic tier 'sonnet' approximation: $3/MTok in, $15/MTok out
    api = (tokens_in / 1e6) * 3.0 + (tokens_out / 1e6) * 15.0
    latency = duration_ms * VALUE_PER_MS
    human = human_minutes * HOURLY_RATE_USD / 60.0

    risk = _risk_factor(confidence) * downstream_cost_usd
    if mode in ("CONSTRAIN", "PROBE"):
        risk *= 0.50      # on retire moitie du risque grace aux contraintes
    elif mode == "ESCALATE":
        risk *= 0.05      # humain elimine 95% du risque
    elif mode == "DEFER":
        risk *= 0.70
    # CONTINUE : on garde 100% du risque restant

    total = api + latency + human + risk
    return CostBreakdown(api_usd=api, latency_usd=latency,
                          human_usd=human, risk_usd=risk, total_usd=total)


def best_mode(
    confidence: float, *, tokens_in: int = 0, tokens_out: int = 0,
    duration_ms: int = 0, downstream_cost_usd: float = 100.0,
    ahmed_minutes_per_escalation: float = 3.0,
) -> dict[str, object]:
    candidates = [
        ("CONTINUE", 0.0),
        ("PROBE", 0.0),
        ("CONSTRAIN", 0.0),
        ("DEFER", 0.0),
        ("ESCALATE", ahmed_minutes_per_escalation),
    ]
    results: list[dict[str, object]] = []
    for mode, human in candidates:
        cb = estimate(
            confidence=confidence, mode=mode,
            tokens_in=tokens_in, tokens_out=tokens_out,
            duration_ms=duration_ms, human_minutes=human,
            downstream_cost_usd=downstream_cost_usd,
        )
        results.append({"mode": mode, "cost": cb.to_dict()})
    results.sort(key=lambda r: r["cost"]["total_usd"])
    return {"best": results[0]["mode"], "ranking": results}
