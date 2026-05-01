"""Client HTTP pour l'API Hostinger.

Production-ready mais **les corps reseau sont marques `# pragma: no cover`**.
Aucun appel reel emis tant que `UBA_LIVE_HOSTINGER=1` n'est pas defini.
Pour les tests on utilise `StubHostingerClient`.

Garde-fou supplementaire : les operations facturables (achat domaine,
creation VPS) **exigent** un `payment_id` non vide AVANT meme l'appel
au client.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Final

import httpx

logger = logging.getLogger(__name__)


HOSTINGER_DEFAULT_BASE: Final[str] = "https://developers.hostinger.com/api/v1"
LIVE_GATE_ENV: Final[str] = "UBA_LIVE_HOSTINGER"


class HostingerAPIError(RuntimeError):
    """Erreur generique cote API Hostinger (4xx/5xx, parse fail, timeout)."""


class HostingerLiveDisabledError(RuntimeError):
    """Tentative d'appel reel alors que `UBA_LIVE_HOSTINGER` != 1."""


class PaymentIdRequiredError(RuntimeError):
    """Operation facturable sans payment_id (sera levee avant tout appel)."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"payment_id requis pour l'operation {operation!r}"
        )
        self.operation = operation


@dataclass(frozen=True)
class HostingerCallResult:
    status_code: int
    json_body: dict[str, Any]
    latency_ms: int
    raw: dict[str, Any]


def is_live_enabled() -> bool:
    return os.environ.get(LIVE_GATE_ENV, "0").strip() == "1"


def require_payment_id(operation: str, payment_id: str | None) -> str:
    """Garde-fou : operation facturable bloquee sans payment_id."""
    if not payment_id or len(payment_id.strip()) < 8:
        raise PaymentIdRequiredError(operation)
    return payment_id.strip()


class HostingerClient:
    """Wrapper REST authentifie. Pas appele dans les tests."""

    name: str = "hostinger"

    def __init__(
        self,
        *,
        api_key_env: str = "HOSTINGER_API_TOKEN",
        base_url: str = HOSTINGER_DEFAULT_BASE,
        timeout_s: float = 30.0,
    ) -> None:
        self._api_key_env = api_key_env
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        api_key = os.environ.get(self._api_key_env, "").strip()
        if not api_key:
            raise HostingerAPIError(
                f"{self._api_key_env} non defini",
            )
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "uba-studio/9G (saas-factory)",
        }

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        require_live: bool = True,
    ) -> HostingerCallResult:
        """Garde fail-closed : si UBA_LIVE_HOSTINGER != 1 et require_live=True,
        leve `HostingerLiveDisabledError` AVANT tout appel reseau.
        """
        if require_live and not is_live_enabled():
            raise HostingerLiveDisabledError(
                f"UBA_LIVE_HOSTINGER!=1 — appel {method} {path} bloque"
            )
        return await self._do_request(
            method=method, path=path, json_body=json_body, params=params,
        )

    async def _do_request(  # pragma: no cover - integration only
        self,
        *,
        method: str,
        path: str,
        json_body: dict[str, Any] | None,
        params: dict[str, str] | None,
    ) -> HostingerCallResult:
        url = self._base_url + (path if path.startswith("/") else "/" + path)
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                resp = await client.request(
                    method.upper(), url,
                    headers=self._headers(),
                    json=json_body, params=params,
                )
        except httpx.HTTPError as exc:
            raise HostingerAPIError(f"network error: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            body = resp.json() if resp.content else {}
        except json.JSONDecodeError as exc:
            raise HostingerAPIError(
                f"reponse non-JSON ({resp.status_code}): {exc}"
            ) from exc

        if resp.status_code >= 400:
            raise HostingerAPIError(
                f"hostinger {resp.status_code}: {body.get('message', 'unknown')}"
            )
        return HostingerCallResult(
            status_code=resp.status_code,
            json_body=body if isinstance(body, dict) else {"items": body},
            latency_ms=latency_ms,
            raw={"url": url, "method": method.upper()},
        )


# ---------------------------------------------------------------------------
# Stub : utilise par les tests
# ---------------------------------------------------------------------------
class StubHostingerClient:
    """Stub : repond avec des `canned_responses` indexees par (method, path_prefix)."""

    name: str = "stub-hostinger"

    def __init__(
        self,
        canned: dict[str, HostingerCallResult] | None = None,
    ) -> None:
        # Cles : "GET /domains/check", "POST /vps/instances", ...
        self._canned: dict[str, HostingerCallResult] = canned or {}
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def set_response(
        self,
        method: str,
        path: str,
        *,
        status_code: int = 200,
        json_body: dict[str, Any] | None = None,
        latency_ms: int = 50,
    ) -> None:
        key = f"{method.upper()} {path}"
        self._canned[key] = HostingerCallResult(
            status_code=status_code,
            json_body=json_body or {},
            latency_ms=latency_ms,
            raw={"stub": True},
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        require_live: bool = True,
    ) -> HostingerCallResult:
        # Le stub IGNORE require_live (tests offline).
        self.calls.append((method.upper(), path, json_body))
        key = f"{method.upper()} {path}"
        if key not in self._canned:
            raise HostingerAPIError(
                f"stub: pas de reponse cannee pour {key}"
            )
        return self._canned[key]
