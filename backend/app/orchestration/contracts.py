"""Contract loader - charge et valide les contrats JSON des agents.

Chaque agent possede un contrat declaratif dans `app/agent_contracts/<agent_id>.json`.
Le loader :
- charge tous les contrats au demarrage
- verifie que chaque `REAL_AGENT` dispose d'un contrat
- offre `validate_inputs/validate_outputs` avec les regles (required, type, enum)
- detecte les violations (contract_violation) -> evidence_ledger
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "agent_contracts"


@dataclass
class Contract:
    agent_id: str
    version: str
    mission: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    timeout_s: int = 60
    budget_max_usd: float = 0.0
    causes_refus: list[str] = field(default_factory=list)
    criteres_succes: list[str] = field(default_factory=list)


_CACHE: dict[str, Contract] = {}


def load_all() -> dict[str, Contract]:
    """Charge (et met en cache) tous les contrats du dossier."""
    if _CACHE:
        return _CACHE
    for f in sorted(CONTRACTS_DIR.glob("*.json")):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("contract %s invalide: %s", f.name, exc)
            continue
        _CACHE[raw["agent_id"]] = Contract(
            agent_id=raw["agent_id"],
            version=raw.get("version", "0.0.0"),
            mission=raw.get("mission", ""),
            inputs=raw.get("inputs", {}),
            outputs=raw.get("outputs", {}),
            permissions=raw.get("permissions", []),
            timeout_s=int(raw.get("timeout_s", 60)),
            budget_max_usd=float(raw.get("budget_max_usd", 0.0)),
            causes_refus=raw.get("causes_refus", []),
            criteres_succes=raw.get("criteres_succes", []),
        )
    logger.info("contracts: %d loaded", len(_CACHE))
    return _CACHE


def get(agent_id: str) -> Contract | None:
    if not _CACHE:
        load_all()
    return _CACHE.get(agent_id)


def _check_type(name: str, val: Any, expected: str | None) -> str | None:
    if expected == "string" and not isinstance(val, str):
        return f"input '{name}' type mismatch: expected string"
    if expected == "integer" and not isinstance(val, int):
        return f"input '{name}' type mismatch: expected integer"
    if expected == "object" and not isinstance(val, dict | object):
        return f"input '{name}' type mismatch: expected object"
    return None


def _check_constraints(name: str, val: Any, schema: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if schema.get("type") == "string" and isinstance(val, str):
        min_len = schema.get("min_length", 0)
        if len(val) < min_len:
            out.append(f"input '{name}' too short: {len(val)} < {min_len}")
    if "enum" in schema and val not in schema["enum"]:
        out.append(f"input '{name}' not in enum: got {val!r}")
    return out


def _validate_one_input(name: str, schema: dict[str, Any],
                         payload: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if schema.get("required") and name not in payload:
        out.append(f"input '{name}' required but missing")
    if name in payload:
        err = _check_type(name, payload[name], schema.get("type"))
        if err:
            out.append(err)
        out.extend(_check_constraints(name, payload[name], schema))
    return out


def validate_inputs(agent_id: str, payload: dict[str, Any]) -> list[str]:
    """Retourne une liste de violations pour les inputs declares required."""
    contract = get(agent_id)
    if not contract:
        return [f"No contract registered for {agent_id}"]
    violations: list[str] = []
    for name, schema in contract.inputs.items():
        if isinstance(schema, dict):
            violations.extend(_validate_one_input(name, schema, payload))
    return violations


def missing_contracts_for(agent_ids: list[str]) -> list[str]:
    """Retourne la liste des agent_id sans contrat."""
    load_all()
    return [aid for aid in agent_ids if aid not in _CACHE]
