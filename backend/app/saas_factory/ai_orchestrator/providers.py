"""Providers IA derriere un Protocol unique.

`AIProvider` est l'interface attendue : `name`, et `call(prompt, system,
max_tokens, **kwargs) -> AIResponse`.

Implementations :

- `StubAIProvider`     : retourne du canned, utilise par les tests
- `ClaudeAIProvider`   : wrap le SDK `anthropic` officiel
- `PerplexityAIProvider`: wrap l'API Perplexity (httpx)
- `ManusAIProvider`     : wrap l'API Manus (httpx)
- `InternalAIProvider`  : retourne une reponse canonique locale (V8.5 stub)

**Phase 9D ne fait AUCUN appel reel** : les providers reels sont definis
mais leur `call()` n'est jamais invoque dans les tests. Le branchement live
necessitera un GO explicite Ahmed (cout par requete).
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

import httpx

logger = logging.getLogger(__name__)


class AIProviderError(RuntimeError):
    """Erreur generique cote provider (auth, parse, format)."""


@dataclass(frozen=True)
class AIResponse:
    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    provider: str
    raw: dict[str, Any] = field(default_factory=dict)


# -----------------------------------------------------------------------------
# Tarification (USD per 1M tokens). A maintenir a jour, sinon CostGuard sous-estime.
# Defaults Claude Sonnet 4.6 / Perplexity sonar / Manus generic / Internal=0.
# -----------------------------------------------------------------------------
PROVIDER_PRICING: Final[dict[str, tuple[float, float]]] = {
    "claude":     (3.00, 15.00),     # Sonnet 4.6 input / output per 1M
    "perplexity": (1.00, 1.00),      # estimation moyenne sonar
    "manus":      (5.00, 25.00),     # estimation conservatrice
    "internal":   (0.00, 0.00),      # local heuristique
}


def _cost_usd(provider: str, tokens_in: int, tokens_out: int) -> float:
    rates = PROVIDER_PRICING.get(provider, (0.0, 0.0))
    return (tokens_in / 1_000_000) * rates[0] + (tokens_out / 1_000_000) * rates[1]


class AIProvider(Protocol):
    name: str

    async def call(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2000,
        timeout_s: float = 30.0,
        **kwargs: Any,
    ) -> AIResponse: ...


# -----------------------------------------------------------------------------
# Stub : utilise par les tests et l'Internal fallback.
# -----------------------------------------------------------------------------
class StubAIProvider:
    """Provider stub : retourne `canned_text` pour chaque appel."""

    name: str = "stub"

    def __init__(
        self,
        canned_text: str = "stub-response",
        *,
        tokens_in: int = 100,
        tokens_out: int = 200,
        latency_ms: int = 50,
        provider_name: str = "stub",
        raise_exc: Exception | None = None,
        provider_for_pricing: str = "internal",
    ) -> None:
        self._canned = canned_text
        self._tokens_in = tokens_in
        self._tokens_out = tokens_out
        self._latency_ms = latency_ms
        self.name = provider_name
        self._raise = raise_exc
        self._pricing_provider = provider_for_pricing
        self.call_count = 0

    async def call(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2000,
        timeout_s: float = 30.0,
        **kwargs: Any,
    ) -> AIResponse:
        self.call_count += 1
        if self._raise is not None:
            raise self._raise
        return AIResponse(
            text=self._canned,
            tokens_in=self._tokens_in,
            tokens_out=self._tokens_out,
            cost_usd=_cost_usd(self._pricing_provider,
                               self._tokens_in, self._tokens_out),
            latency_ms=self._latency_ms,
            provider=self.name,
            raw={"stub": True},
        )


# -----------------------------------------------------------------------------
# Claude (Anthropic SDK officiel)
# -----------------------------------------------------------------------------
class ClaudeAIProvider:
    """Wrap le SDK `anthropic`. Pas appele dans les tests."""

    name: str = "claude"

    def __init__(
        self,
        *,
        api_key_env: str = "ANTHROPIC_API_KEY",
        model: str = "claude-sonnet-4-6",
    ) -> None:
        self._api_key_env = api_key_env
        self._model = model
        self._client: Any | None = None

    def _client_lazy(self) -> Any:
        if self._client is None:
            api_key = os.environ.get(self._api_key_env, "").strip()
            if not api_key:
                raise AIProviderError(
                    f"{self._api_key_env} non defini pour Claude provider"
                )
            self._client = self._instantiate_client(api_key)
        return self._client

    def _instantiate_client(self, api_key: str) -> Any:  # pragma: no cover
        # Integration only — exclu de la coverage unitaire (depend du SDK).
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise AIProviderError(f"anthropic SDK indisponible: {exc}") from exc
        return AsyncAnthropic(api_key=api_key)

    async def call(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2000,
        timeout_s: float = 30.0,
        **kwargs: Any,
    ) -> AIResponse:
        client = self._client_lazy()
        return await self._do_call(client, prompt, system, max_tokens, timeout_s)

    async def _do_call(  # pragma: no cover - integration only
        self, client: Any, prompt: str, system: str | None,
        max_tokens: int, timeout_s: float,
    ) -> AIResponse:
        started = time.perf_counter()
        try:
            resp = await client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system or "",
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout_s,
            )
        except Exception as exc:
            raise AIProviderError(f"claude call failed: {exc}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        text = ""
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", "") == "text":
                text += getattr(block, "text", "")
        usage = getattr(resp, "usage", None)
        tokens_in = int(getattr(usage, "input_tokens", 0)) if usage else 0
        tokens_out = int(getattr(usage, "output_tokens", 0)) if usage else 0
        return AIResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=_cost_usd("claude", tokens_in, tokens_out),
            latency_ms=latency_ms,
            provider="claude",
            raw={"model": self._model, "stop_reason": getattr(resp, "stop_reason", None)},
        )


# -----------------------------------------------------------------------------
# Perplexity (httpx)
# -----------------------------------------------------------------------------
class PerplexityAIProvider:
    name: str = "perplexity"

    def __init__(
        self,
        *,
        api_key_env: str = "PERPLEXITY_API_KEY",
        model: str = "sonar-pro",
        endpoint: str = "https://api.perplexity.ai/chat/completions",
    ) -> None:
        self._api_key_env = api_key_env
        self._model = model
        self._endpoint = endpoint

    async def call(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2000,
        timeout_s: float = 30.0,
        **kwargs: Any,
    ) -> AIResponse:
        api_key = os.environ.get(self._api_key_env, "").strip()
        if not api_key:
            raise AIProviderError(f"{self._api_key_env} non defini")
        return await self._do_call(api_key, prompt, system, max_tokens, timeout_s)

    async def _do_call(  # pragma: no cover - integration only
        self, api_key: str, prompt: str, system: str | None,
        max_tokens: int, timeout_s: float,
    ) -> AIResponse:
        msgs: list[dict[str, str]] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        body = {"model": self._model, "messages": msgs, "max_tokens": max_tokens}
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                r = await client.post(
                    self._endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"perplexity call failed: {exc}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        choices = data.get("choices", [])
        text = choices[0]["message"]["content"] if choices else ""
        usage = data.get("usage", {}) or {}
        tokens_in = int(usage.get("prompt_tokens", 0))
        tokens_out = int(usage.get("completion_tokens", 0))
        return AIResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=_cost_usd("perplexity", tokens_in, tokens_out),
            latency_ms=latency_ms,
            provider="perplexity",
            raw={"model": self._model},
        )


# -----------------------------------------------------------------------------
# Manus (httpx)
# -----------------------------------------------------------------------------
class ManusAIProvider:
    name: str = "manus"

    def __init__(
        self,
        *,
        api_key_env: str = "MANUS_API_KEY",
        endpoint: str = "https://api.manus.im/v1/chat",
    ) -> None:
        self._api_key_env = api_key_env
        self._endpoint = endpoint

    async def call(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2000,
        timeout_s: float = 60.0,
        **kwargs: Any,
    ) -> AIResponse:
        api_key = os.environ.get(self._api_key_env, "").strip()
        if not api_key:
            raise AIProviderError(f"{self._api_key_env} non defini")
        return await self._do_call(api_key, prompt, system, max_tokens, timeout_s)

    async def _do_call(  # pragma: no cover - integration only
        self, api_key: str, prompt: str, system: str | None,
        max_tokens: int, timeout_s: float,
    ) -> AIResponse:
        body = {
            "system": system or "",
            "prompt": prompt,
            "max_tokens": max_tokens,
        }
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                r = await client.post(
                    self._endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=body,
                )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as exc:
            raise AIProviderError(f"manus call failed: {exc}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)
        text = data.get("text", "") or json.dumps(data)
        tokens_in = int(data.get("tokens_in", 0))
        tokens_out = int(data.get("tokens_out", 0))
        return AIResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=_cost_usd("manus", tokens_in, tokens_out),
            latency_ms=latency_ms,
            provider="manus",
            raw=data,
        )


# -----------------------------------------------------------------------------
# Internal (V8.5 — fallback local sans appel externe)
# -----------------------------------------------------------------------------
class InternalAIProvider:
    """Provider local : reponse canonique a cout zero. Utilise en fallback
    ultime si tous les providers externes echouent.
    """

    name: str = "internal"

    def __init__(self, *, canned_text: str = "{}") -> None:
        self._canned = canned_text

    async def call(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 2000,
        timeout_s: float = 30.0,
        **kwargs: Any,
    ) -> AIResponse:
        return AIResponse(
            text=self._canned,
            tokens_in=len(prompt) // 4,
            tokens_out=len(self._canned) // 4,
            cost_usd=0.0,
            latency_ms=1,
            provider="internal",
            raw={"internal": True},
        )
