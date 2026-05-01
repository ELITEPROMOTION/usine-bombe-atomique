"""AIRouter : orchestre le choix de provider, le budget, la boucle, le retry.

Pipeline d'un appel `route()` :

  1. Pre-check budget (CostGuard.estimate_cost + pre_check)
       -> BudgetExceededError si depasse
  2. Pick provider (poids RoutingPolicy.weights ou override hint)
  3. Try with retry exponential ; sur echec terminal, tente le suivant
     dans `RoutingPolicy.fallback_order`
  4. Apres reponse : LoopDetector.record(prompt, text) — peut lever
  5. CostGuard.register_actual()
  6. DecisionsLogger.log(...)
  7. Retourne RouterDecision(response, retries, fallback_used)

Les erreurs `BudgetExceededError` et `LoopDetectedError` ne declenchent
pas de fallback : elles signalent un probleme metier qui doit etre traite
upstream (handoff Ahmed, ajustement budget). Les erreurs provider
(timeout, 5xx, parse) declenchent le fallback.
"""
from __future__ import annotations

import logging
import random
import secrets
from dataclasses import dataclass, field
from typing import Final

import asyncpg

from app.saas_factory.ai_orchestrator.cost_guard import (
    BudgetExceededError,
    CostGuard,
)
from app.saas_factory.ai_orchestrator.decisions_logger import DecisionsLogger
from app.saas_factory.ai_orchestrator.loop_detector import (
    LoopDetectedError,
    LoopDetector,
)
from app.saas_factory.ai_orchestrator.providers import (
    AIProvider,
    AIProviderError,
    AIResponse,
)
from app.saas_factory.ai_orchestrator.retry import (
    RetryExhaustedError,
    TransientAIError,
    with_retry,
)

logger = logging.getLogger(__name__)


# Defaults Phase 9B : Claude 80% / Perplexity 15% / Manus 5% / Internal 0%
DEFAULT_WEIGHTS: Final[dict[str, int]] = {
    "claude": 80, "perplexity": 15, "manus": 5, "internal": 0,
}
DEFAULT_FALLBACK: Final[tuple[str, ...]] = ("claude", "perplexity", "manus", "internal")


@dataclass(frozen=True)
class RoutingPolicy:
    weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    fallback_order: tuple[str, ...] = DEFAULT_FALLBACK
    allow_fallback: bool = True
    max_attempts_per_provider: int = 3
    base_delay_s: float = 0.5


@dataclass(frozen=True)
class RouterDecision:
    response: AIResponse
    requested_provider: str
    actual_provider: str
    fallback_used: bool
    retries_total: int
    providers_tried: tuple[str, ...]


class RouterFailureError(RuntimeError):
    """Tous les providers de la chaine ont echoue."""

    def __init__(self, last_exc: BaseException, providers_tried: tuple[str, ...]):
        super().__init__(
            f"all providers failed (tried {providers_tried}): {last_exc}"
        )
        self.last_exc = last_exc
        self.providers_tried = providers_tried


def _validate_weights(weights: dict[str, int]) -> None:
    total = sum(int(v) for v in weights.values())
    if total != 100:
        raise ValueError(f"weights doivent sommer a 100 (actuel: {total})")
    if any(v < 0 for v in weights.values()):
        raise ValueError("weights >= 0 requis")


def _weighted_choice(
    weights: dict[str, int], rng: random.Random,
) -> str:
    """Pick pondere : 80/15/5/0 -> 'claude' 80% du temps, etc."""
    _validate_weights(weights)
    pop = list(weights.keys())
    wts = [weights[k] for k in pop]
    return rng.choices(pop, weights=wts, k=1)[0]


class AIRouter:
    def __init__(
        self,
        pool: asyncpg.Pool,
        providers: dict[str, AIProvider],
        *,
        cost_guard: CostGuard,
        loop_detector: LoopDetector,
        decisions_logger: DecisionsLogger,
        policy: RoutingPolicy | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if not providers:
            raise ValueError("providers non vide requis")
        self._pool = pool
        self._providers = providers
        self._cost_guard = cost_guard
        self._loop_detector = loop_detector
        self._logger = decisions_logger
        self._policy = policy or RoutingPolicy()
        # SystemRandom par defaut : Random-subclass, pas flag bandit B311.
        self._rng = rng or secrets.SystemRandom()

    def _pick_initial(self, hint: str | None) -> str:
        if hint is not None:
            if hint not in self._providers:
                raise ValueError(f"hint provider inconnu: {hint!r}")
            return hint
        return _weighted_choice(self._policy.weights, self._rng)

    def _fallback_after(self, current: str) -> list[str]:
        """Liste des providers a essayer apres `current` (ordre policy)."""
        if not self._policy.allow_fallback:
            return []
        seen = {current}
        out: list[str] = []
        for name in self._policy.fallback_order:
            if name in seen:
                continue
            if name not in self._providers:
                continue
            out.append(name)
            seen.add(name)
        return out

    async def route(
        self,
        *,
        project_id: str,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2000,
        hint: str | None = None,
    ) -> RouterDecision:
        if not prompt.strip():
            raise ValueError("prompt vide")

        requested = self._pick_initial(hint)

        # Pre-check budget (estimation : on prend le tarif du provider voulu)
        cost_estimate = CostGuard.estimate_cost_usd(
            provider=requested, prompt_chars=len(prompt), max_tokens=max_tokens,
        )
        try:
            self._cost_guard.pre_check(
                project_id=project_id, cost_estimate_usd=cost_estimate,
            )
        except BudgetExceededError as exc:
            await self._logger.log(
                project_id=project_id,
                requested_provider=requested,
                actual_provider=requested,
                status="budget_blocked",
                prompt=prompt, response_text=None,
                error_msg=str(exc),
            )
            raise

        order = [requested, *self._fallback_after(requested)]
        retries_total = 0
        providers_tried: list[str] = []
        last_exc: BaseException | None = None

        for idx, provider_name in enumerate(order):
            providers_tried.append(provider_name)
            provider = self._providers[provider_name]
            try:
                response, attempts = await self._call_with_retry(
                    provider=provider, prompt=prompt, system=system,
                    max_tokens=max_tokens,
                )
                retries_total += attempts - 1

                # Loop detector : peut lever LoopDetectedError
                try:
                    self._loop_detector.record(
                        project_id=project_id,
                        prompt=prompt,
                        response_text=response.text,
                    )
                except LoopDetectedError as loop_exc:
                    await self._logger.log(
                        project_id=project_id,
                        requested_provider=requested,
                        actual_provider=provider_name,
                        status="loop_blocked",
                        prompt=prompt, response_text=response.text,
                        tokens_in=response.tokens_in,
                        tokens_out=response.tokens_out,
                        cost_usd=response.cost_usd,
                        latency_ms=response.latency_ms,
                        fallback_used=idx > 0,
                        retries=retries_total,
                        loop_detected=True,
                        error_msg=str(loop_exc),
                    )
                    self._cost_guard.register_actual(
                        project_id=project_id, cost_usd=response.cost_usd,
                    )
                    raise

                # Succes
                self._cost_guard.register_actual(
                    project_id=project_id, cost_usd=response.cost_usd,
                )
                await self._logger.log(
                    project_id=project_id,
                    requested_provider=requested,
                    actual_provider=provider_name,
                    status="fallback" if idx > 0 else "ok",
                    prompt=prompt, response_text=response.text,
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
                    cost_usd=response.cost_usd,
                    latency_ms=response.latency_ms,
                    fallback_used=idx > 0,
                    retries=retries_total,
                )
                return RouterDecision(
                    response=response,
                    requested_provider=requested,
                    actual_provider=provider_name,
                    fallback_used=idx > 0,
                    retries_total=retries_total,
                    providers_tried=tuple(providers_tried),
                )

            except RetryExhaustedError as exc:
                retries_total += self._policy.max_attempts_per_provider
                last_exc = exc
                logger.info(
                    "router: %s retry exhausted, trying fallback (idx=%d)",
                    provider_name, idx,
                )
                continue
            except AIProviderError as exc:
                # Erreur terminale du provider (auth, format) -> fallback direct
                last_exc = exc
                logger.info("router: %s terminal error, fallback: %s",
                            provider_name, exc)
                continue

        # Tous les providers ont echoue
        err_msg = str(last_exc) if last_exc else "unknown"
        await self._logger.log(
            project_id=project_id,
            requested_provider=requested,
            actual_provider=providers_tried[-1] if providers_tried else requested,
            status="error",
            prompt=prompt, response_text=None,
            fallback_used=len(providers_tried) > 1,
            retries=retries_total,
            error_msg=err_msg,
        )
        raise RouterFailureError(last_exc or RuntimeError("no providers tried"),
                                  tuple(providers_tried))

    async def _call_with_retry(
        self,
        *,
        provider: AIProvider,
        prompt: str,
        system: str | None,
        max_tokens: int,
    ) -> tuple[AIResponse, int]:
        """Returns (response, attempts_used)."""
        attempt_counter = {"n": 0}

        async def _factory() -> AIResponse:
            attempt_counter["n"] += 1
            try:
                return await provider.call(
                    prompt=prompt, system=system, max_tokens=max_tokens,
                )
            except TransientAIError:
                raise
            except AIProviderError:
                # erreur terminale : pas de retry
                raise
            except Exception as exc:
                # Tout le reste : on classe comme transient pour donner sa chance.
                raise TransientAIError(str(exc)) from exc

        response = await with_retry(
            _factory,
            max_attempts=self._policy.max_attempts_per_provider,
            base_delay=self._policy.base_delay_s,
        )
        return response, attempt_counter["n"]
