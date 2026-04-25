"""V8 OSINT module #3 — Dendani dependency scanner.

Wrappe pip-audit + safety + npm audit + Trivy pour les projets Dendani.
Scope : projets Dendani uniquement (dendani_only sur le project_path).

Sources externes : NVD CVE database (consume only).
Risk level : medium.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from app.osint.legal_framework import (
    RiskLevel,
    ScopeViolationError,
    log_osint_action,
    rate_limit_strict,
)

logger = logging.getLogger("uba.osint.dep_scanner")

DENDANI_PROJECT_ROOTS = (
    "/repo",
    "/app",
    "/srv/dendani",
)


def _ensure_dendani_path(path: str) -> Path:
    p = Path(path).resolve()
    for root in DENDANI_PROJECT_ROOTS:
        if str(p).startswith(root):
            return p
    raise ScopeViolationError(f"path {p} outside Dendani project roots")


def _run(cmd: list[str], cwd: Path, timeout: int = 120) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        return {"rc": proc.returncode, "stdout": proc.stdout[:50_000],
                "stderr": proc.stderr[:5_000]}
    except FileNotFoundError:
        return {"rc": -127, "skipped": f"{cmd[0]} not installed"}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "error": "timeout"}


@rate_limit_strict(max_per_hour=20)
@log_osint_action(risk_level=RiskLevel.MEDIUM, module="dendani_dep_scanner")
async def scan_python(target: str, _actor: str = "scheduler",
                       _consent_id: str | None = None) -> dict[str, Any]:
    """pip-audit + safety sur un projet Python Dendani."""
    project = _ensure_dendani_path(target)
    pip_audit = _run(["pip-audit", "--format", "json", "--strict",
                      "-r", str(project / "requirements.txt")], project, timeout=180)
    safety = _run(["safety", "check", "--json", "--full-report",
                   "-r", str(project / "requirements.txt")], project, timeout=180)

    findings: list[dict[str, Any]] = []
    if pip_audit.get("rc") == 0 or pip_audit.get("rc") == 1:
        try:
            data = json.loads(pip_audit.get("stdout") or "[]")
            for entry in data if isinstance(data, list) else data.get("dependencies", []):
                vulns = entry.get("vulns") if isinstance(entry, dict) else None
                if vulns:
                    for v in vulns:
                        findings.append({
                            "tool": "pip-audit",
                            "package": entry.get("name"),
                            "id": v.get("id"),
                            "severity": v.get("severity") or "unknown",
                            "fix_versions": v.get("fix_versions", []),
                        })
        except json.JSONDecodeError:
            pass

    if safety.get("rc") in (0, 64):
        try:
            data = json.loads(safety.get("stdout") or "[]")
            for v in data if isinstance(data, list) else []:
                findings.append({
                    "tool": "safety",
                    "package": v[0] if len(v) > 0 else None,
                    "id": v[4] if len(v) > 4 else None,
                    "severity": "high",
                })
        except (json.JSONDecodeError, IndexError):
            pass

    return {"target": str(project), "tools_run": ["pip-audit", "safety"],
            "findings_count": len(findings), "findings": findings[:200]}


@rate_limit_strict(max_per_hour=20)
@log_osint_action(risk_level=RiskLevel.MEDIUM, module="dendani_dep_scanner")
async def scan_npm(target: str, _actor: str = "scheduler",
                    _consent_id: str | None = None) -> dict[str, Any]:
    """npm audit sur un projet JS Dendani."""
    project = _ensure_dendani_path(target)
    if not (project / "package.json").exists():
        return {"target": str(project), "skipped": "no package.json"}
    out = _run(["npm", "audit", "--json"], project, timeout=120)
    findings: list[dict[str, Any]] = []
    if out.get("stdout"):
        try:
            data = json.loads(out["stdout"])
            for k, v in (data.get("vulnerabilities") or {}).items():
                findings.append({
                    "tool": "npm-audit",
                    "package": k,
                    "severity": v.get("severity"),
                    "via_count": len(v.get("via", [])),
                })
        except json.JSONDecodeError:
            pass
    return {"target": str(project), "tool": "npm-audit",
            "findings_count": len(findings), "findings": findings[:200]}


@rate_limit_strict(max_per_hour=20)
@log_osint_action(risk_level=RiskLevel.MEDIUM, module="dendani_dep_scanner")
async def scan_docker_image(target: str, _actor: str = "scheduler",
                             _consent_id: str | None = None) -> dict[str, Any]:
    """Trivy scan d'une image Docker Dendani (image label/repository must contain dendani)."""
    if "dendani" not in target.lower() and not target.startswith(("uba-", "dendani/")):
        raise ScopeViolationError(f"image {target} not Dendani-tagged")
    out = _run(["trivy", "image", "--format", "json", "--severity",
                "HIGH,CRITICAL", target], Path("/tmp"), timeout=300)
    findings: list[dict[str, Any]] = []
    if out.get("stdout"):
        try:
            data = json.loads(out["stdout"])
            for res in data.get("Results", []) or []:
                for v in res.get("Vulnerabilities", []) or []:
                    findings.append({
                        "tool": "trivy",
                        "id": v.get("VulnerabilityID"),
                        "package": v.get("PkgName"),
                        "severity": v.get("Severity"),
                        "title": (v.get("Title") or "")[:120],
                    })
        except json.JSONDecodeError:
            pass
    return {"target": target, "tool": "trivy",
            "findings_count": len(findings), "findings": findings[:200]}


__all__ = ["scan_python", "scan_npm", "scan_docker_image"]
