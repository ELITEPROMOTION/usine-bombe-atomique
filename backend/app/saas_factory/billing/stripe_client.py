"""Client Stripe minimaliste (httpx + Bearer + HMAC webhook signature).

Production-ready mais `_do_call` marque pragma:no-cover. Aucun appel reel
emis sans `UBA_LIVE_STRIPE=1`.

Le SDK officiel `stripe` n'est PAS une dependance dure : on parle a
l'API REST directement via httpx. Cela simplifie l'isolation des tests
et evite un cout d'apprentissage du SDK pour ce wrapper minimal.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)


STRIPE_API_BASE: Final[str] = "https://api.stripe.com/v1"
LIVE_GATE_ENV: Final[str] = "UBA_LIVE_STRIPE"
WEBHOOK_TOLERANCE_S: Final[int] = 300  # 5 minutes


class StripeAPIError(RuntimeError):
    """Erreur generique cote Stripe (4xx/5xx, parse fail, timeout)."""


class StripeLiveDisabledError(RuntimeError):
    """Tentative d'appel reel sans `UBA_LIVE_STRIPE=1`."""


class StripeSignatureError(RuntimeError):
    """Signature webhook invalide (replay ou forge)."""


@dataclass(frozen=True)
class StripeCallResult:
    status_code: int
    json_body: dict[str, Any]
    latency_ms: int


def is_live_enabled() -> bool:
    return os.environ.get(LIVE_GATE_ENV, "0").strip() == "1"


def verify_webhook_signature(
    *,
    payload: str,
    signature_header: str,
    webhook_secret: str,
    tolerance_s: int = WEBHOOK_TOLERANCE_S,
    now: float | None = None,
) -> None:
    """Verifie le header `Stripe-Signature` (format `t=<ts>,v1=<sig>`).

    Leve `StripeSignatureError` si :
    - format invalide
    - timestamp trop ancien (replay)
    - HMAC ne match pas
    """
    if not signature_header:
        raise StripeSignatureError("signature header manquant")
    if not webhook_secret:
        raise StripeSignatureError("webhook_secret vide")

    parts: dict[str, str] = {}
    for kv in signature_header.split(","):
        if "=" not in kv:
            continue
        k, v = kv.strip().split("=", 1)
        # Plusieurs v1 possibles (rotation) — on garde le 1er pour test puis
        # on les verifie tous plus bas.
        if k in parts and k.startswith("v"):
            parts[k] += "," + v
        else:
            parts[k] = v

    ts_str = parts.get("t")
    if ts_str is None:
        raise StripeSignatureError("timestamp absent du header")
    try:
        ts = int(ts_str)
    except ValueError as exc:
        raise StripeSignatureError("timestamp non entier") from exc

    current = now if now is not None else time.time()
    if abs(current - ts) > tolerance_s:
        raise StripeSignatureError(
            f"timestamp hors tolerance ({abs(current - ts):.0f}s)"
        )

    signed_payload = f"{ts}.{payload}".encode()
    expected_sigs: list[str] = []
    for k, v in parts.items():
        if k.startswith("v"):
            expected_sigs.extend(s.strip() for s in v.split(",") if s.strip())
    if not expected_sigs:
        raise StripeSignatureError("aucune signature v1+ dans le header")

    computed = hmac.new(
        webhook_secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    if not any(hmac.compare_digest(computed, s) for s in expected_sigs):
        raise StripeSignatureError("signature ne match pas")


class StripeClient:
    """Wrapper REST httpx. Pas appele dans les tests."""

    name: str = "stripe"

    def __init__(
        self,
        *,
        api_key_env: str = "STRIPE_API_KEY",
        webhook_secret_env: str = "STRIPE_WEBHOOK_SECRET",
        base_url: str = STRIPE_API_BASE,
        timeout_s: float = 30.0,
    ) -> None:
        self._api_key_env = api_key_env
        self._webhook_secret_env = webhook_secret_env
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        api_key = os.environ.get(self._api_key_env, "").strip()
        if not api_key:
            raise StripeAPIError(f"{self._api_key_env} non defini")
        return {
            "Authorization": f"Bearer {api_key}",
            "Stripe-Version": "2024-09-30.acacia",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "uba-studio/9H",
        }

    def webhook_secret(self) -> str:
        return os.environ.get(self._webhook_secret_env, "").strip()

    async def request(
        self,
        method: str,
        path: str,
        *,
        form_data: dict[str, Any] | None = None,
        require_live: bool = True,
    ) -> StripeCallResult:
        if require_live and not is_live_enabled():
            raise StripeLiveDisabledError(
                f"UBA_LIVE_STRIPE!=1 — appel {method} {path} bloque"
            )
        return await self._do_call(method=method, path=path, form_data=form_data)

    async def _do_call(  # pragma: no cover - integration only
        self,
        *,
        method: str,
        path: str,
        form_data: dict[str, Any] | None,
    ) -> StripeCallResult:
        url = self._base_url + (path if path.startswith("/") else "/" + path)
        body: bytes | None = None
        if form_data:
            # Stripe utilise du form-encoded (pas du JSON)
            body = urlencode(_flatten_form(form_data)).encode("utf-8")

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                resp = await client.request(
                    method.upper(), url,
                    headers=self._headers(),
                    content=body,
                )
        except httpx.HTTPError as exc:
            raise StripeAPIError(f"network error: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            payload = resp.json() if resp.content else {}
        except json.JSONDecodeError as exc:
            raise StripeAPIError(f"reponse non-JSON: {exc}") from exc
        if resp.status_code >= 400:
            err = payload.get("error", {}) or {}
            raise StripeAPIError(
                f"stripe {resp.status_code}: {err.get('message', 'unknown')}"
            )
        return StripeCallResult(
            status_code=resp.status_code, json_body=payload,
            latency_ms=latency_ms,
        )


def _flatten_form(d: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """Stripe form-encoding : dict imbrique -> 'parent[child]=value'."""
    out: list[tuple[str, str]] = []
    for k, v in d.items():
        key = f"{prefix}[{k}]" if prefix else str(k)
        if isinstance(v, dict):
            out.extend(_flatten_form(v, key))
        elif isinstance(v, list | tuple):
            for i, item in enumerate(v):
                ikey = f"{key}[{i}]"
                if isinstance(item, dict):
                    out.extend(_flatten_form(item, ikey))
                else:
                    out.append((ikey, str(item)))
        elif v is None:
            continue
        elif isinstance(v, bool):
            out.append((key, "true" if v else "false"))
        else:
            out.append((key, str(v)))
    return out


# ---------------------------------------------------------------------------
# Stub
# ---------------------------------------------------------------------------
class StubStripeClient:
    """Stub Stripe : repond avec des canned responses pour les tests."""

    name: str = "stub-stripe"

    def __init__(self) -> None:
        self._canned: dict[str, StripeCallResult] = {}
        self._webhook_secret: str = "whsec_stub"
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def set_response(
        self, method: str, path: str, *,
        status_code: int = 200, json_body: dict[str, Any] | None = None,
        latency_ms: int = 30,
    ) -> None:
        self._canned[f"{method.upper()} {path}"] = StripeCallResult(
            status_code=status_code, json_body=json_body or {},
            latency_ms=latency_ms,
        )

    def set_webhook_secret(self, secret: str) -> None:
        self._webhook_secret = secret

    def webhook_secret(self) -> str:
        return self._webhook_secret

    async def request(
        self, method: str, path: str, *,
        form_data: dict[str, Any] | None = None,
        require_live: bool = True,
    ) -> StripeCallResult:
        self.calls.append((method.upper(), path, form_data))
        key = f"{method.upper()} {path}"
        if key not in self._canned:
            raise StripeAPIError(f"stub: pas de canned pour {key}")
        return self._canned[key]
