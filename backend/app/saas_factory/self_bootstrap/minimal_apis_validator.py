"""Module A : validation des 4 secrets minimaux requis pour amorcer V9.

Lit ANTHROPIC_API_KEY / MANUS_API_KEY / PERPLEXITY_API_KEY / HOSTINGER_API_TOKEN
depuis os.environ exclusivement (jamais de hardcode), verifie format et
optionnellement la connectivite TCP/TLS du host (zero appel facturable).

Le validator ne logue jamais la valeur des secrets : il ne manipule
que des booleens et des prefixes/longueurs.
"""
from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

ServiceName = Literal["anthropic", "manus", "perplexity", "hostinger"]
ConnectivityState = Literal["unknown", "ok", "fail"]


@dataclass(frozen=True)
class ServiceSpec:
    env_var: str
    expected_prefix: tuple[str, ...]
    min_length: int
    host: str
    port: int = 443


# Specs : prefixes documentes par chaque provider.
# Hostinger ne publie pas de prefixe stable -> on se contente d'une longueur
# minimale et d'une regex basique.
SERVICE_SPECS: dict[ServiceName, ServiceSpec] = {
    "anthropic": ServiceSpec(
        env_var="ANTHROPIC_API_KEY",
        expected_prefix=("sk-ant-",),
        min_length=40,
        host="api.anthropic.com",
    ),
    "manus": ServiceSpec(
        env_var="MANUS_API_KEY",
        expected_prefix=("sk-",),
        min_length=20,
        host="api.manus.im",
    ),
    "perplexity": ServiceSpec(
        env_var="PERPLEXITY_API_KEY",
        expected_prefix=("pplx-",),
        min_length=20,
        host="api.perplexity.ai",
    ),
    "hostinger": ServiceSpec(
        env_var="HOSTINGER_API_TOKEN",
        expected_prefix=(),  # pas de prefixe officiel stable
        min_length=20,
        host="developers.hostinger.com",
    ),
}


@dataclass
class ServiceCheck:
    service: ServiceName
    present: bool
    format_ok: bool
    connectivity: ConnectivityState = "unknown"
    masked_hint: str = ""        # 4 derniers caracteres seulement, jamais la cle complete
    message: str = ""


@dataclass
class ValidationOutcome:
    all_present: bool
    all_format_ok: bool
    all_reachable: bool
    services: dict[ServiceName, ServiceCheck] = field(default_factory=dict)

    def is_pass(self, *, require_connectivity: bool = False) -> bool:
        if not self.all_present or not self.all_format_ok:
            return False
        return self.all_reachable if require_connectivity else True

    def summary(self) -> dict[str, dict[str, str | bool]]:
        return {
            svc: {
                "present": chk.present,
                "format_ok": chk.format_ok,
                "connectivity": chk.connectivity,
                "hint": chk.masked_hint,
                "message": chk.message,
            }
            for svc, chk in self.services.items()
        }


class MinimalApisValidator:
    """Verifie la presence + format des 4 secrets de bootstrap.

    Aucune valeur n'est jamais loguee ou retournee : seuls les 4 derniers
    caracteres apparaissent dans `masked_hint` pour aider au debug.
    """

    def __init__(self, env: dict[str, str] | None = None) -> None:
        # Permet l'injection pour les tests.
        self._env = env if env is not None else os.environ

    def _check_format(self, spec: ServiceSpec, value: str) -> tuple[bool, str]:
        if len(value) < spec.min_length:
            return False, f"trop court ({len(value)} < {spec.min_length})"
        if spec.expected_prefix and not value.startswith(spec.expected_prefix):
            prefixes = " ou ".join(spec.expected_prefix)
            return False, f"prefixe attendu : {prefixes}"
        return True, "format ok"

    def _check_connectivity(self, spec: ServiceSpec, timeout: float) -> ConnectivityState:
        """TCP socket connect — n'envoie aucune requete HTTP, donc zero credit."""
        try:
            with socket.create_connection((spec.host, spec.port), timeout=timeout):
                return "ok"
        except OSError as exc:
            logger.debug("connectivity %s: %s", spec.host, exc)
            return "fail"

    def validate(
        self,
        *,
        check_connectivity: bool = False,
        timeout: float = 3.0,
    ) -> ValidationOutcome:
        services: dict[ServiceName, ServiceCheck] = {}
        all_present = True
        all_format_ok = True
        all_reachable = True

        for svc_name, spec in SERVICE_SPECS.items():
            raw = self._env.get(spec.env_var, "").strip()
            present = bool(raw)
            if not present:
                services[svc_name] = ServiceCheck(
                    service=svc_name,
                    present=False,
                    format_ok=False,
                    connectivity="unknown",
                    message=f"variable {spec.env_var} absente ou vide",
                )
                all_present = False
                all_format_ok = False
                all_reachable = False
                continue

            format_ok, fmt_msg = self._check_format(spec, raw)
            if not format_ok:
                all_format_ok = False

            hint = f"...{raw[-4:]}" if len(raw) >= 8 else "..."

            connectivity: ConnectivityState = "unknown"
            if check_connectivity:
                connectivity = self._check_connectivity(spec, timeout)
                if connectivity != "ok":
                    all_reachable = False

            services[svc_name] = ServiceCheck(
                service=svc_name,
                present=True,
                format_ok=format_ok,
                connectivity=connectivity,
                masked_hint=hint,
                message=fmt_msg,
            )

        if not check_connectivity:
            # Si on n'a pas teste la connectivite, on ne peut rien affirmer.
            all_reachable = False

        return ValidationOutcome(
            all_present=all_present,
            all_format_ok=all_format_ok,
            all_reachable=all_reachable,
            services=services,
        )
