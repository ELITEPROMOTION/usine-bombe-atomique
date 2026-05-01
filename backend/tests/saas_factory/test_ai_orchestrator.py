"""Tests Phase 9D — AI Orchestrator (providers + router + cost guard +
loop detector + retry + decisions logger + qualification adapter).

Tous les appels externes (Claude / Perplexity / Manus / httpx / anthropic)
sont mockes ou stubbes. AUCUN appel reel emis.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.saas_factory.ai_orchestrator.cost_guard import (
    BudgetExceededError,
    CostGuard,
    CostLimits,
)
from app.saas_factory.ai_orchestrator.decisions_logger import (
    PREVIEW_LEN,
    DecisionsLogger,
    _preview,
    _short_hash,
)
from app.saas_factory.ai_orchestrator.loop_detector import (
    LoopDetectedError,
    LoopDetector,
)
from app.saas_factory.ai_orchestrator.providers import (
    PROVIDER_PRICING,
    AIProviderError,
    ClaudeAIProvider,
    InternalAIProvider,
    ManusAIProvider,
    PerplexityAIProvider,
    StubAIProvider,
    _cost_usd,
)
from app.saas_factory.ai_orchestrator.qualification_adapter import (
    RouterBackedClaudeProvider,
)
from app.saas_factory.ai_orchestrator.retry import (
    RetryExhaustedError,
    TransientAIError,
    with_retry,
)
from app.saas_factory.ai_orchestrator.router import (
    DEFAULT_FALLBACK,
    DEFAULT_WEIGHTS,
    AIRouter,
    RouterFailureError,
    RoutingPolicy,
    _validate_weights,
    _weighted_choice,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_pool() -> tuple[MagicMock, MagicMock]:
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=0.0)
    conn.execute = AsyncMock()
    return pool, conn


# ===========================================================================
# Providers
# ===========================================================================
class TestStubAIProvider:
    @pytest.mark.asyncio
    async def test_returns_canned_text(self) -> None:
        s = StubAIProvider("hello")
        r = await s.call(prompt="x")
        assert r.text == "hello"
        assert r.provider == "stub"
        assert r.tokens_in == 100
        assert s.call_count == 1

    @pytest.mark.asyncio
    async def test_raises_when_configured(self) -> None:
        s = StubAIProvider(raise_exc=TransientAIError("boom"))
        with pytest.raises(TransientAIError):
            await s.call(prompt="x")

    @pytest.mark.asyncio
    async def test_cost_calc_consistent_with_provider_pricing(self) -> None:
        s = StubAIProvider(tokens_in=1_000_000, tokens_out=1_000_000,
                           provider_for_pricing="claude")
        r = await s.call(prompt="x")
        # Claude: 3$/M input + 15$/M output -> 18$
        assert abs(r.cost_usd - 18.0) < 0.001


class TestProviderPricing:
    def test_pricing_table_has_4_providers(self) -> None:
        assert {"claude", "perplexity", "manus", "internal"} <= set(PROVIDER_PRICING)

    def test_internal_is_zero_cost(self) -> None:
        assert PROVIDER_PRICING["internal"] == (0.0, 0.0)

    def test_cost_usd_helper_zero_for_unknown(self) -> None:
        assert _cost_usd("ghost", 1_000_000, 1_000_000) == 0.0


class TestRealProvidersConstruction:
    """Ne fait que construire — n'appelle PAS l'API externe."""

    def test_claude_provider_constructs(self) -> None:
        p = ClaudeAIProvider()
        assert p.name == "claude"

    def test_perplexity_provider_constructs(self) -> None:
        p = PerplexityAIProvider()
        assert p.name == "perplexity"

    def test_manus_provider_constructs(self) -> None:
        p = ManusAIProvider()
        assert p.name == "manus"

    @pytest.mark.asyncio
    async def test_internal_provider_returns_canned(self) -> None:
        p = InternalAIProvider(canned_text='{"ok":true}')
        r = await p.call(prompt="hello")
        assert r.text == '{"ok":true}'
        assert r.cost_usd == 0.0
        assert r.provider == "internal"

    @pytest.mark.asyncio
    async def test_claude_raises_when_no_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            p = ClaudeAIProvider()
            with pytest.raises(AIProviderError, match="ANTHROPIC_API_KEY"):
                await p.call(prompt="x")

    @pytest.mark.asyncio
    async def test_perplexity_raises_when_no_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PERPLEXITY_API_KEY", None)
            p = PerplexityAIProvider()
            with pytest.raises(AIProviderError, match="PERPLEXITY_API_KEY"):
                await p.call(prompt="x")

    @pytest.mark.asyncio
    async def test_manus_raises_when_no_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MANUS_API_KEY", None)
            p = ManusAIProvider()
            with pytest.raises(AIProviderError, match="MANUS_API_KEY"):
                await p.call(prompt="x")


# ===========================================================================
# Retry
# ===========================================================================
class TestWithRetry:
    @pytest.mark.asyncio
    async def test_succeeds_first_try(self) -> None:
        async def factory() -> int:
            return 42
        result = await with_retry(factory, max_attempts=3, base_delay=0.0)
        assert result == 42

    @pytest.mark.asyncio
    async def test_succeeds_after_2_failures(self) -> None:
        attempts = {"n": 0}
        sleeps: list[float] = []

        async def fake_sleep(d: float) -> None:
            sleeps.append(d)

        async def factory() -> str:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise TransientAIError("retry me")
            return "ok"

        result = await with_retry(
            factory, max_attempts=3, base_delay=1.0, jitter=False,
            sleep=fake_sleep,
        )
        assert result == "ok"
        assert attempts["n"] == 3
        # 2 sleeps : delay 1s puis 2s (exponential)
        assert len(sleeps) == 2
        assert sleeps[0] == 1.0
        assert sleeps[1] == 2.0

    @pytest.mark.asyncio
    async def test_exhaustion_raises(self) -> None:
        async def fake_sleep(_d: float) -> None:
            return

        async def factory() -> None:
            raise TransientAIError("nope")

        with pytest.raises(RetryExhaustedError) as exc_info:
            await with_retry(factory, max_attempts=2, sleep=fake_sleep)
        assert exc_info.value.attempts == 2
        assert isinstance(exc_info.value.last_exc, TransientAIError)

    @pytest.mark.asyncio
    async def test_non_transient_propagates_immediately(self) -> None:
        attempts = {"n": 0}

        async def factory() -> None:
            attempts["n"] += 1
            raise ValueError("terminal")

        with pytest.raises(ValueError):
            await with_retry(factory, max_attempts=3)
        # 1 seul appel (pas de retry sur ValueError)
        assert attempts["n"] == 1

    def test_zero_max_attempts_rejected(self) -> None:
        async def factory() -> int: return 1
        with pytest.raises(ValueError):
            asyncio.get_event_loop().run_until_complete(
                with_retry(factory, max_attempts=0)
            )

    @pytest.mark.asyncio
    async def test_jitter_applies_random_factor(self) -> None:
        sleeps: list[float] = []

        async def fake_sleep(d: float) -> None:
            sleeps.append(d)

        attempts = {"n": 0}

        async def factory() -> int:
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise TransientAIError("once")
            return 1

        await with_retry(
            factory, max_attempts=3, base_delay=10.0,
            jitter=True, sleep=fake_sleep,
        )
        # avec jitter : delay in [0.5*10, 1.5*10] = [5, 15]
        assert 5.0 <= sleeps[0] <= 15.0


# ===========================================================================
# LoopDetector
# ===========================================================================
class TestLoopDetector:
    def test_first_record_is_fine(self) -> None:
        ld = LoopDetector(threshold=3, window_seconds=300)
        ld.record(project_id="p", prompt="A", response_text="X")

    def test_third_identical_pair_raises(self) -> None:
        ld = LoopDetector(threshold=3, window_seconds=300)
        ld.record(project_id="p", prompt="A", response_text="X")
        ld.record(project_id="p", prompt="A", response_text="X")
        with pytest.raises(LoopDetectedError):
            ld.record(project_id="p", prompt="A", response_text="X")

    def test_different_project_isolated(self) -> None:
        ld = LoopDetector(threshold=2)
        ld.record(project_id="p1", prompt="A", response_text="X")
        ld.record(project_id="p2", prompt="A", response_text="X")
        # Pas encore 2 sur le meme projet -> ok
        ld.record(project_id="p1", prompt="B", response_text="X")

    def test_different_pairs_dont_trigger(self) -> None:
        ld = LoopDetector(threshold=3)
        ld.record(project_id="p", prompt="A", response_text="X")
        ld.record(project_id="p", prompt="A", response_text="Y")
        ld.record(project_id="p", prompt="B", response_text="X")
        # 3 enregistrements mais aucune paire identique 3x
        ld.record(project_id="p", prompt="A", response_text="X")  # 2x "A|X"

    def test_threshold_below_2_rejected(self) -> None:
        with pytest.raises(ValueError):
            LoopDetector(threshold=1)

    def test_old_entries_evicted(self) -> None:
        clock = [1000.0]
        ld = LoopDetector(threshold=2, window_seconds=10, clock=lambda: clock[0])
        ld.record(project_id="p", prompt="A", response_text="X")
        # avance > window
        clock[0] = 1100.0
        # nouvelle record : la 1ere est evictee, donc compteur = 1, pas de loop
        ld.record(project_id="p", prompt="A", response_text="X")

    def test_reset_clears_state(self) -> None:
        ld = LoopDetector(threshold=2)
        ld.record(project_id="p", prompt="A", response_text="X")
        ld.reset("p")
        ld.record(project_id="p", prompt="A", response_text="X")  # ok, compteur reset
        assert "p" in ld.stats()

    def test_reset_all_clears_everything(self) -> None:
        ld = LoopDetector(threshold=2)
        ld.record(project_id="p1", prompt="A", response_text="X")
        ld.record(project_id="p2", prompt="B", response_text="Y")
        ld.reset()
        assert ld.stats() == {}


# ===========================================================================
# CostGuard
# ===========================================================================
class TestCostGuard:
    @pytest.mark.asyncio
    async def test_reload_aggregates_per_project(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = [
            {"project_id": "p1", "total": 1.5},
            {"project_id": "p2", "total": 0.25},
        ]
        conn.fetchval.return_value = 1.75
        cg = CostGuard(pool, limits=CostLimits())
        await cg.reload_from_db()
        assert cg.project_spent("p1") == 1.5
        assert cg.project_spent("p2") == 0.25
        assert cg.daily_spent() == 1.75

    def test_per_call_cap_blocks(self) -> None:
        pool, _ = _mock_pool()
        cg = CostGuard(pool, limits=CostLimits(per_call_cap_usd=0.01))
        with pytest.raises(BudgetExceededError, match="per_call"):
            cg.pre_check(project_id="p", cost_estimate_usd=0.05)

    def test_per_project_cap_blocks(self) -> None:
        pool, _ = _mock_pool()
        cg = CostGuard(pool, limits=CostLimits(
            per_call_cap_usd=10.0, per_project_cap_usd=1.0,
        ))
        cg.register_actual(project_id="p", cost_usd=0.9)
        with pytest.raises(BudgetExceededError, match="per_project"):
            cg.pre_check(project_id="p", cost_estimate_usd=0.5)

    def test_daily_cap_blocks(self) -> None:
        pool, _ = _mock_pool()
        cg = CostGuard(pool, limits=CostLimits(
            per_call_cap_usd=10.0, per_project_cap_usd=1000.0,
            daily_cap_usd=2.0,
        ))
        cg.register_actual(project_id="p", cost_usd=1.5)
        with pytest.raises(BudgetExceededError, match="daily"):
            cg.pre_check(project_id="p", cost_estimate_usd=1.0)

    def test_register_actual_increments_counters(self) -> None:
        pool, _ = _mock_pool()
        cg = CostGuard(pool)
        cg.register_actual(project_id="p", cost_usd=0.30)
        cg.register_actual(project_id="p", cost_usd=0.20)
        assert abs(cg.project_spent("p") - 0.50) < 1e-9
        assert abs(cg.daily_spent() - 0.50) < 1e-9

    def test_register_actual_zero_or_negative_ignored(self) -> None:
        pool, _ = _mock_pool()
        cg = CostGuard(pool)
        cg.register_actual(project_id="p", cost_usd=0.0)
        cg.register_actual(project_id="p", cost_usd=-1.0)
        assert cg.project_spent("p") == 0.0

    def test_estimate_cost_usd_static(self) -> None:
        # Claude: 3$/M input * (1000 chars / 4 / 1M) + 15$/M output * 0.001M
        # = 0.00075 + 0.015 = 0.01575
        c = CostGuard.estimate_cost_usd(
            provider="claude", prompt_chars=1000, max_tokens=1000,
        )
        assert abs(c - 0.01575) < 1e-6

    def test_estimate_unknown_provider_zero(self) -> None:
        c = CostGuard.estimate_cost_usd(
            provider="ghost", prompt_chars=1000, max_tokens=1000,
        )
        assert c == 0.0


# ===========================================================================
# DecisionsLogger
# ===========================================================================
class TestDecisionsLogger:
    @pytest.mark.asyncio
    async def test_log_inserts_with_hash_not_raw(self) -> None:
        pool, conn = _mock_pool()
        new_id = uuid4()
        conn.fetchrow.return_value = {"decision_id": new_id}
        dl = DecisionsLogger(pool)
        prompt = "supersecret-prompt-content"
        rid = await dl.log(
            project_id="p", requested_provider="claude",
            actual_provider="claude", status="ok",
            prompt=prompt, response_text="resp",
            tokens_in=100, tokens_out=200, cost_usd=0.01, latency_ms=300,
        )
        assert rid == new_id
        # SQL appele
        sql = conn.fetchrow.await_args_list[0].args[0]
        assert "INSERT INTO ai_decisions_log" in sql
        # Aucun argument ne contient le prompt brut au-dela de PREVIEW_LEN.
        # Plus precisement : prompt_hash = sha256, prompt_preview = prompt court.
        # Pour un prompt court (< PREVIEW_LEN), preview = prompt entier (pas un leak,
        # c'est intentionnel pour le debug).
        # Mais le hash doit etre present.
        prompt_hash_arg = conn.fetchrow.await_args_list[0].args[5]
        assert prompt_hash_arg == _short_hash(prompt)

    @pytest.mark.asyncio
    async def test_long_prompt_truncated_in_preview(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"decision_id": uuid4()}
        dl = DecisionsLogger(pool)
        long_prompt = "x" * (PREVIEW_LEN + 50)
        await dl.log(
            project_id="p", requested_provider="claude",
            actual_provider="claude", status="ok",
            prompt=long_prompt, response_text=None,
        )
        preview_arg = conn.fetchrow.await_args_list[0].args[6]
        assert len(preview_arg) == PREVIEW_LEN
        assert preview_arg == "x" * PREVIEW_LEN

    @pytest.mark.asyncio
    async def test_stats_for_project_aggregates(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "calls": 10, "total_cost": 0.15, "tokens_in": 1500,
            "tokens_out": 3000, "fallbacks": 2, "loops": 0, "errors": 1,
        }
        dl = DecisionsLogger(pool)
        stats = await dl.stats_for_project("p")
        assert stats["calls"] == 10
        assert stats["total_cost"] == 0.15

    def test_preview_helper(self) -> None:
        assert _preview(None) is None
        assert _preview("short") == "short"
        long_s = "y" * (PREVIEW_LEN + 10)
        assert len(_preview(long_s)) == PREVIEW_LEN

    def test_short_hash_helper(self) -> None:
        h = _short_hash("abc")
        assert len(h) == 64

    @pytest.mark.asyncio
    async def test_log_truncates_long_error_msg_and_provider(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"decision_id": uuid4()}
        dl = DecisionsLogger(pool)
        await dl.log(
            project_id="p", requested_provider="x" * 100,
            actual_provider="y" * 100, status="error",
            prompt="p", response_text=None, error_msg="z" * 1000,
        )
        # Args : args[0]=SQL ; les VALUES sont dans args[1..16].
        # Ordre : project_id, requested, actual, status, prompt_hash,
        # prompt_preview, response_preview, tokens_in, tokens_out, cost_usd,
        # latency_ms, fallback_used, retries, loop_detected, error_msg, metadata
        args = conn.fetchrow.await_args_list[0].args
        assert len(args[2]) <= 32        # requested_provider
        assert len(args[3]) <= 32        # actual_provider
        assert args[15] is not None       # error_msg
        assert len(args[15]) <= 500


# ===========================================================================
# AIRouter
# ===========================================================================
class TestRouterUtils:
    def test_validate_weights_rejects_non_100(self) -> None:
        with pytest.raises(ValueError):
            _validate_weights({"a": 50, "b": 30})

    def test_validate_weights_rejects_negative(self) -> None:
        with pytest.raises(ValueError):
            _validate_weights({"a": 110, "b": -10})

    def test_weighted_choice_deterministic_with_seed(self) -> None:
        rng = random.Random(42)
        # Avec poids 100 sur 'claude', toujours claude.
        for _ in range(20):
            picked = _weighted_choice({"claude": 100, "perplexity": 0}, rng)
            assert picked == "claude"

    def test_weighted_choice_rejects_no_positive(self) -> None:
        rng = random.Random()
        with pytest.raises(ValueError):
            _weighted_choice({"a": 0, "b": 0}, rng)


class TestAIRouter:
    def _build_router(
        self,
        *,
        providers: dict | None = None,
        weights: dict[str, int] | None = None,
        rng_seed: int = 0,
    ) -> tuple[AIRouter, MagicMock, MagicMock, CostGuard, LoopDetector,
                MagicMock]:
        pool, _conn = _mock_pool()
        cg = CostGuard(pool, limits=CostLimits(
            per_call_cap_usd=100.0, per_project_cap_usd=1000.0,
            daily_cap_usd=10000.0,
        ))
        ld = LoopDetector(threshold=3, window_seconds=300)
        dlog = MagicMock()
        dlog.log = AsyncMock(return_value=uuid4())
        if providers is None:
            providers = {
                "claude": StubAIProvider("claude-resp", provider_name="claude",
                                         provider_for_pricing="claude"),
                "perplexity": StubAIProvider("perp-resp", provider_name="perplexity",
                                              provider_for_pricing="perplexity"),
                "internal": InternalAIProvider(canned_text="internal"),
            }
        if weights is None:
            weights = {"claude": 100, "perplexity": 0, "internal": 0}
        policy = RoutingPolicy(
            weights=weights,
            fallback_order=("claude", "perplexity", "internal"),
            base_delay_s=0.0,
        )
        router = AIRouter(
            pool, providers, cost_guard=cg, loop_detector=ld,
            decisions_logger=dlog, policy=policy,
            rng=random.Random(rng_seed),
        )
        return router, providers["claude"], providers["perplexity"], cg, ld, dlog

    @pytest.mark.asyncio
    async def test_route_uses_weighted_pick(self) -> None:
        router, claude, _pp, _cg, _ld, _dl = self._build_router()
        decision = await router.route(
            project_id="p", prompt="test prompt", max_tokens=100,
        )
        assert decision.actual_provider == "claude"
        assert decision.fallback_used is False
        assert decision.response.text == "claude-resp"
        assert claude.call_count == 1

    @pytest.mark.asyncio
    async def test_route_honors_hint(self) -> None:
        router, _claude, pp, _cg, _ld, _dl = self._build_router()
        decision = await router.route(
            project_id="p", prompt="test", hint="perplexity",
        )
        assert decision.actual_provider == "perplexity"
        assert pp.call_count == 1

    @pytest.mark.asyncio
    async def test_route_unknown_hint_raises(self) -> None:
        router, *_ = self._build_router()
        with pytest.raises(ValueError, match="hint"):
            await router.route(project_id="p", prompt="test", hint="ghost")

    @pytest.mark.asyncio
    async def test_route_fallback_when_primary_fails(self) -> None:
        # claude leve TransientAIError -> retry epuise -> fallback perplexity
        claude_failing = StubAIProvider(
            provider_name="claude",
            raise_exc=TransientAIError("rate limit"),
        )
        pp_ok = StubAIProvider("ok-from-perp", provider_name="perplexity")
        providers = {
            "claude": claude_failing,
            "perplexity": pp_ok,
            "internal": InternalAIProvider(),
        }
        router, *_ = self._build_router(providers=providers)
        decision = await router.route(
            project_id="p", prompt="test prompt", max_tokens=100,
        )
        assert decision.fallback_used is True
        assert decision.actual_provider == "perplexity"
        assert decision.response.text == "ok-from-perp"
        assert "claude" in decision.providers_tried
        assert "perplexity" in decision.providers_tried

    @pytest.mark.asyncio
    async def test_route_all_fail_raises(self) -> None:
        all_fail = {
            n: StubAIProvider(
                provider_name=n, raise_exc=TransientAIError("nope"),
            )
            for n in ("claude", "perplexity", "internal")
        }
        router, *_ = self._build_router(providers=all_fail)
        with pytest.raises(RouterFailureError):
            await router.route(project_id="p", prompt="test")

    @pytest.mark.asyncio
    async def test_route_empty_prompt_raises(self) -> None:
        router, *_ = self._build_router()
        with pytest.raises(ValueError):
            await router.route(project_id="p", prompt="   ")

    @pytest.mark.asyncio
    async def test_budget_blocks_before_call(self) -> None:
        pool, _conn = _mock_pool()
        cg = CostGuard(pool, limits=CostLimits(per_call_cap_usd=0.000001))
        ld = LoopDetector()
        dlog = MagicMock()
        dlog.log = AsyncMock(return_value=uuid4())
        claude = StubAIProvider(provider_name="claude")
        router = AIRouter(
            pool, {"claude": claude},
            cost_guard=cg, loop_detector=ld, decisions_logger=dlog,
            policy=RoutingPolicy(weights={"claude": 100}, fallback_order=("claude",)),
        )
        with pytest.raises(BudgetExceededError):
            await router.route(project_id="p", prompt="big prompt " * 100)
        # Le provider n'a jamais ete appele
        assert claude.call_count == 0
        # Mais une ligne 'budget_blocked' a ete loguee
        log_calls = dlog.log.await_args_list
        assert any(c.kwargs.get("status") == "budget_blocked" for c in log_calls)

    @pytest.mark.asyncio
    async def test_loop_detected_after_n_identical_responses(self) -> None:
        # Claude renvoie toujours le meme texte, donc on detecte la boucle
        # apres `threshold` appels identiques.
        router, *_ = self._build_router()
        # 1er et 2e appel : ok ; 3e : LoopDetectedError
        await router.route(project_id="p", prompt="same prompt")
        await router.route(project_id="p", prompt="same prompt")
        with pytest.raises(LoopDetectedError):
            await router.route(project_id="p", prompt="same prompt")

    @pytest.mark.asyncio
    async def test_no_providers_rejected_at_construction(self) -> None:
        pool, _ = _mock_pool()
        cg = CostGuard(pool)
        ld = LoopDetector()
        dlog = MagicMock()
        with pytest.raises(ValueError):
            AIRouter(pool, {}, cost_guard=cg, loop_detector=ld,
                     decisions_logger=dlog)

    def test_default_weights_sum_to_100(self) -> None:
        assert sum(DEFAULT_WEIGHTS.values()) == 100

    def test_default_fallback_order_includes_internal_last(self) -> None:
        assert DEFAULT_FALLBACK[-1] == "internal"


# ===========================================================================
# RouterBackedClaudeProvider (qualification adapter)
# ===========================================================================
class TestQualificationAdapter:
    @pytest.mark.asyncio
    async def test_adapter_parses_json_response(self) -> None:
        # On construit un router stub qui retourne du JSON.
        router = MagicMock()
        canned = {"key": "value", "n": 42}
        router.route = AsyncMock(return_value=MagicMock(
            response=MagicMock(text=json.dumps(canned)),
            actual_provider="claude",
        ))
        adapter = RouterBackedClaudeProvider(router, project_id="p")
        result = await adapter.analyze_cdc(
            cdc_text="some cdc", system_prompt="sp",
        )
        assert result == canned

    @pytest.mark.asyncio
    async def test_adapter_handles_markdown_wrapped_json(self) -> None:
        router = MagicMock()
        wrapped = "```json\n" + json.dumps({"a": 1}) + "\n```"
        router.route = AsyncMock(return_value=MagicMock(
            response=MagicMock(text=wrapped),
            actual_provider="perplexity",
        ))
        adapter = RouterBackedClaudeProvider(router, project_id="p")
        result = await adapter.analyze_cdc(
            cdc_text="cdc", system_prompt="sp",
        )
        assert result == {"a": 1}

    @pytest.mark.asyncio
    async def test_adapter_raises_on_non_json(self) -> None:
        router = MagicMock()
        router.route = AsyncMock(return_value=MagicMock(
            response=MagicMock(text="this is not json"),
            actual_provider="claude",
        ))
        adapter = RouterBackedClaudeProvider(router, project_id="p")
        with pytest.raises(ValueError, match="JSON"):
            await adapter.analyze_cdc(cdc_text="cdc", system_prompt="sp")

    @pytest.mark.asyncio
    async def test_adapter_passes_project_id_to_router(self) -> None:
        router = MagicMock()
        router.route = AsyncMock(return_value=MagicMock(
            response=MagicMock(text="{}"),
            actual_provider="claude",
        ))
        adapter = RouterBackedClaudeProvider(router, project_id="proj-X")
        await adapter.analyze_cdc(cdc_text="cdc", system_prompt="sp")
        call_kwargs = router.route.await_args.kwargs
        assert call_kwargs["project_id"] == "proj-X"
        assert call_kwargs["prompt"] == "cdc"
        assert call_kwargs["system"] == "sp"


# ===========================================================================
# Couverture supplementaire : chemins moins frequents
# ===========================================================================
class TestExtraCoverage:
    """Tests pour pousser router/cost_guard/loop_detector au-dela de 99%."""

    def test_cost_guard_limits_property(self) -> None:
        pool, _ = _mock_pool()
        custom = CostLimits(
            per_call_cap_usd=1.0, per_project_cap_usd=10.0, daily_cap_usd=100.0,
        )
        cg = CostGuard(pool, limits=custom)
        assert cg.limits is custom

    def test_loop_detector_lru_eviction_when_max_projects_tracked(self) -> None:
        from app.saas_factory.ai_orchestrator.loop_detector import (
            MAX_PROJECTS_TRACKED,
        )
        ld = LoopDetector(threshold=10)
        # Remplit au-dela de la capacite
        for i in range(MAX_PROJECTS_TRACKED + 5):
            ld.record(project_id=f"p{i}", prompt="q", response_text="r")
        # Le LRU evicte les plus anciens : on a au plus MAX_PROJECTS_TRACKED entrees
        assert len(ld.stats()) == MAX_PROJECTS_TRACKED
        # Les premiers ('p0' a 'p4') ont ete evinces
        assert "p0" not in ld.stats()
        assert f"p{MAX_PROJECTS_TRACKED + 4}" in ld.stats()

    @pytest.mark.asyncio
    async def test_router_allow_fallback_false_no_secondary_attempt(self) -> None:
        # claude leve TransientAIError, pas de fallback autorise -> RouterFailure
        pool, _ = _mock_pool()
        cg = CostGuard(pool)
        ld = LoopDetector()
        dlog = MagicMock()
        dlog.log = AsyncMock(return_value=uuid4())
        claude = StubAIProvider(
            provider_name="claude",
            raise_exc=TransientAIError("rate-limited"),
        )
        pp = StubAIProvider("pp-ok", provider_name="perplexity")
        router = AIRouter(
            pool, {"claude": claude, "perplexity": pp},
            cost_guard=cg, loop_detector=ld, decisions_logger=dlog,
            policy=RoutingPolicy(
                weights={"claude": 100, "perplexity": 0},
                fallback_order=("claude", "perplexity"),
                allow_fallback=False,
                base_delay_s=0.0,
            ),
            rng=random.Random(0),
        )
        with pytest.raises(RouterFailureError):
            await router.route(project_id="p", prompt="hello")
        # perplexity n'a jamais ete tente
        assert pp.call_count == 0

    @pytest.mark.asyncio
    async def test_router_fallback_skips_unknown_provider_in_order(self) -> None:
        # fallback_order mentionne 'ghost' qui n'est pas dans providers : on saute.
        pool, _ = _mock_pool()
        cg = CostGuard(pool)
        ld = LoopDetector()
        dlog = MagicMock()
        dlog.log = AsyncMock(return_value=uuid4())
        claude = StubAIProvider(
            provider_name="claude",
            raise_exc=TransientAIError("nope"),
        )
        pp = StubAIProvider("pp-ok", provider_name="perplexity")
        router = AIRouter(
            pool, {"claude": claude, "perplexity": pp},
            cost_guard=cg, loop_detector=ld, decisions_logger=dlog,
            policy=RoutingPolicy(
                weights={"claude": 100, "perplexity": 0},
                fallback_order=("claude", "ghost", "perplexity"),
                base_delay_s=0.0,
            ),
            rng=random.Random(0),
        )
        decision = await router.route(project_id="p", prompt="hello")
        # On saute 'ghost' et on tombe sur 'perplexity'
        assert decision.actual_provider == "perplexity"
        assert "ghost" not in decision.providers_tried

    @pytest.mark.asyncio
    async def test_router_provider_error_falls_back_immediately(self) -> None:
        # AIProviderError = erreur terminale, pas de retry, fallback direct.
        pool, _ = _mock_pool()
        cg = CostGuard(pool)
        ld = LoopDetector()
        dlog = MagicMock()
        dlog.log = AsyncMock(return_value=uuid4())
        claude_terminal = StubAIProvider(
            provider_name="claude",
            raise_exc=AIProviderError("auth failure"),
        )
        pp = StubAIProvider("pp-ok", provider_name="perplexity")
        router = AIRouter(
            pool, {"claude": claude_terminal, "perplexity": pp},
            cost_guard=cg, loop_detector=ld, decisions_logger=dlog,
            policy=RoutingPolicy(
                weights={"claude": 100, "perplexity": 0},
                fallback_order=("claude", "perplexity"),
                base_delay_s=0.0,
            ),
            rng=random.Random(0),
        )
        decision = await router.route(project_id="p", prompt="hello")
        assert decision.actual_provider == "perplexity"
        assert decision.fallback_used is True
        # 1 seul appel au provider terminal (pas de retry)
        assert claude_terminal.call_count == 1

    @pytest.mark.asyncio
    async def test_router_classifies_unknown_exception_as_transient(self) -> None:
        # Le provider leve une RuntimeError non-classifiee -> classe transient
        # par _call_with_retry, donc retry exponential, puis exhaustion.
        pool, _ = _mock_pool()
        cg = CostGuard(pool)
        ld = LoopDetector()
        dlog = MagicMock()
        dlog.log = AsyncMock(return_value=uuid4())
        claude = StubAIProvider(
            provider_name="claude",
            raise_exc=RuntimeError("unclassified"),
        )
        pp = StubAIProvider("pp-ok", provider_name="perplexity")
        router = AIRouter(
            pool, {"claude": claude, "perplexity": pp},
            cost_guard=cg, loop_detector=ld, decisions_logger=dlog,
            policy=RoutingPolicy(
                weights={"claude": 100, "perplexity": 0},
                fallback_order=("claude", "perplexity"),
                base_delay_s=0.0,
                max_attempts_per_provider=2,
            ),
            rng=random.Random(0),
        )
        decision = await router.route(project_id="p", prompt="hello")
        # Apres 2 retries exhaustives sur claude, fallback sur perplexity
        assert decision.actual_provider == "perplexity"
        assert claude.call_count == 2  # max_attempts_per_provider
