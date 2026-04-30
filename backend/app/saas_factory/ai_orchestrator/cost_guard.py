"""CostGuard : enforce les caps de budget IA par projet et par appel.

Avant chaque appel IA, le router demande au CostGuard `pre_check(cost_estimate)`.
Apres l'appel, il appelle `register_actual(cost_actual)`. Si `pre_check` voit
qu'on franchirait un cap, il leve `BudgetExceededError`.

Source de verite : la table `ai_decisions_log`. Le CostGuard cache en memoire
le total deja depense par projet pour eviter un SELECT par appel — il refresh
le cache via `reload_from_db()` au demarrage de chaque pipeline.

Caps par defaut (USD) :
- per_call_cap_usd     = 5.00     (1 appel ne doit pas exceder 5$)
- per_project_cap_usd  = 50.00    (cumul sur tout le projet)
- daily_cap_usd        = 200.00   (cumul global tous projets confondus / 24h)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CostLimits:
    per_call_cap_usd: float = 5.00
    per_project_cap_usd: float = 50.00
    daily_cap_usd: float = 200.00


class BudgetExceededError(RuntimeError):
    def __init__(self, scope: str, current: float, cap: float) -> None:
        super().__init__(
            f"budget {scope} depasse : current={current:.4f}$ cap={cap:.4f}$"
        )
        self.scope = scope
        self.current = current
        self.cap = cap


class CostGuard:
    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        limits: CostLimits | None = None,
    ) -> None:
        self._pool = pool
        self._limits = limits or CostLimits()
        self._project_total: dict[str, float] = {}     # cache projet -> spent
        self._daily_total: float = 0.0
        self._daily_window_start: datetime | None = None

    @property
    def limits(self) -> CostLimits:
        return self._limits

    async def reload_from_db(self) -> None:
        """Recharge les compteurs depuis ai_decisions_log."""
        async with self._pool.acquire() as conn:
            project_rows = await conn.fetch(
                """
                SELECT project_id, COALESCE(SUM(cost_usd), 0)::FLOAT8 AS total
                  FROM ai_decisions_log
                 GROUP BY project_id
                """,
            )
            now = datetime.now(UTC)
            day_ago = now - timedelta(hours=24)
            daily = await conn.fetchval(
                """
                SELECT COALESCE(SUM(cost_usd), 0)::FLOAT8
                  FROM ai_decisions_log
                 WHERE created_at >= $1
                """,
                day_ago,
            )
        self._project_total = {r["project_id"]: float(r["total"]) for r in project_rows}
        self._daily_total = float(daily or 0.0)
        self._daily_window_start = day_ago

    def pre_check(self, *, project_id: str, cost_estimate_usd: float) -> None:
        """Soulieve `BudgetExceededError` si l'appel ferait franchir un cap.

        cost_estimate_usd doit etre une estimation prudente (input + max_output * rate).
        """
        if cost_estimate_usd > self._limits.per_call_cap_usd:
            raise BudgetExceededError(
                "per_call", cost_estimate_usd, self._limits.per_call_cap_usd,
            )

        project_after = self._project_total.get(project_id, 0.0) + cost_estimate_usd
        if project_after > self._limits.per_project_cap_usd:
            raise BudgetExceededError(
                f"per_project[{project_id}]", project_after,
                self._limits.per_project_cap_usd,
            )

        daily_after = self._daily_total + cost_estimate_usd
        if daily_after > self._limits.daily_cap_usd:
            raise BudgetExceededError(
                "daily", daily_after, self._limits.daily_cap_usd,
            )

    def register_actual(self, *, project_id: str, cost_usd: float) -> None:
        """Met a jour les compteurs en memoire apres un appel reussi."""
        if cost_usd <= 0:
            return
        self._project_total[project_id] = (
            self._project_total.get(project_id, 0.0) + cost_usd
        )
        self._daily_total += cost_usd

    def project_spent(self, project_id: str) -> float:
        return self._project_total.get(project_id, 0.0)

    def daily_spent(self) -> float:
        return self._daily_total

    @staticmethod
    def estimate_cost_usd(
        *,
        provider: str,
        prompt_chars: int,
        max_tokens: int,
    ) -> float:
        """Estimation prudente : input ~ chars/4, output = max_tokens en plein."""
        from app.saas_factory.ai_orchestrator.providers import (
            PROVIDER_PRICING,
        )
        rates = PROVIDER_PRICING.get(provider, (0.0, 0.0))
        tokens_in = max(1, prompt_chars // 4)
        return (
            (tokens_in / 1_000_000) * rates[0]
            + (max_tokens / 1_000_000) * rates[1]
        )
