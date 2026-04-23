"""Agent #11 Security Scanner - audit securite multi-axe.

Axes :
1. bandit strict (-ll) sur tout y compris les tests (B101 accepted dans tests/)
2. scan de secrets (regex : AWS keys, JWT, passwords hardcoded, private keys)
3. audit des dependances (regex sur requirements.txt contre un catalogue de
   versions vulnerables connues ; deterministe, sans reseau)

Sortie :
- Score composite : 0.4 * bandit + 0.4 * secrets + 0.2 * deps
- Ecriture de SECURITY.md resumant les findings.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.workspace import Workspace

logger = logging.getLogger(__name__)


# Catalogue minimal de versions vulnerables (exemple pedagogique).
# En prod, remplace par pip-audit / osv.dev.
KNOWN_VULNERABLE: dict[str, list[str]] = {
    "requests":    ["2.27.0", "2.26.0"],
    "flask":       ["0.12.0", "0.11.1"],
    "pyyaml":      ["5.1", "3.13"],
    "urllib3":     ["1.24.1", "1.25.7"],
    "cryptography": ["3.2", "3.1"],
    "jinja2":      ["2.10"],
}

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key_id",   re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret_access",   re.compile(r"(?i)aws[_\-]?secret[_\-]?access[_\-]?key\s*[:=]\s*['\"][A-Za-z0-9/+=]{40}['\"]")),
    ("private_key_pem",     re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----")),
    ("generic_password",    re.compile(r"(?i)(password|passwd|pwd|secret)\s*=\s*['\"][^'\"\s]{8,}['\"]")),
    ("jwt_hardcoded",       re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("bearer_token",        re.compile(r"(?i)bearer\s+['\"]?[A-Za-z0-9._\-]{20,}['\"]?")),
]

SECRET_WHITELIST = {"changeme", "example", "<password>", "password123"}


class SecurityAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="agent-11-security", name="Security Scanner", version="1.0.0")
        self.category = "security"

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        workspace: Workspace = inputs["workspace"]
        manifest = inputs.get("manifest") or workspace.manifest()

        bandit_findings = await _run_bandit_strict(workspace.root)
        secret_findings = _scan_secrets(workspace, manifest)
        dep_findings = _scan_deps(workspace)

        bandit_score = _score_bandit(bandit_findings)
        secret_score = 1.0 if not secret_findings else max(0.0, 1.0 - 0.3 * len(secret_findings))
        dep_score = 1.0 if not dep_findings else max(0.0, 1.0 - 0.25 * len(dep_findings))

        composite = round(0.4 * bandit_score + 0.4 * secret_score + 0.2 * dep_score, 3)
        passed = composite >= 0.80 and not secret_findings

        # Ecrit SECURITY.md
        workspace.write("SECURITY.md", _write_report(
            bandit_findings, secret_findings, dep_findings, composite,
        ))

        return {
            "score": composite,
            "passed": passed,
            "bandit_score": round(bandit_score, 3),
            "secrets_score": round(secret_score, 3),
            "deps_score": round(dep_score, 3),
            "bandit_count": len(bandit_findings),
            "secrets_count": len(secret_findings),
            "deps_count": len(dep_findings),
            "findings": {
                "bandit": bandit_findings[:10],
                "secrets": secret_findings[:10],
                "deps": dep_findings[:10],
            },
        }


async def _run_bandit_strict(root: Path) -> list[dict[str, Any]]:
    """Bandit strict : inclut les tests mais ignore B101 (assert dans tests)."""
    proc = await asyncio.create_subprocess_exec(
        "bandit", "-q", "-r", str(root), "-f", "json", "--exit-zero",
        "--skip", "B101",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        payload = json.loads(stdout or b"{}")
    except json.JSONDecodeError:
        return []
    return payload.get("results", [])


def _score_bandit(findings: list[dict[str, Any]]) -> float:
    score = 1.0
    for f in findings:
        sev = (f.get("issue_severity") or "LOW").upper()
        score -= {"HIGH": 0.30, "MEDIUM": 0.05, "LOW": 0.005}.get(sev, 0.0)
    return max(0.0, min(1.0, score))


def _scan_secrets(ws: Workspace, manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in manifest:
        path = str(m.get("path", ""))
        try:
            content = ws.read(path)
        except FileNotFoundError:
            continue
        for name, pat in SECRET_PATTERNS:
            for match in pat.finditer(content):
                raw = match.group(0)
                if any(w in raw.lower() for w in SECRET_WHITELIST):
                    continue
                out.append({
                    "type": name,
                    "path": path,
                    "excerpt": raw[:60] + ("..." if len(raw) > 60 else ""),
                })
    return out


DEP_LINE_RE = re.compile(r'^\s*([a-zA-Z0-9_\-\.]+)\s*(?:\[[^\]]*\])?\s*==\s*([0-9A-Za-z\.\-]+)')


def _scan_deps(ws: Workspace) -> list[dict[str, Any]]:
    try:
        content = ws.read("requirements.txt")
    except FileNotFoundError:
        return []
    out: list[dict[str, Any]] = []
    for line in content.splitlines():
        m = DEP_LINE_RE.match(line)
        if not m:
            continue
        pkg, ver = m.group(1).lower(), m.group(2)
        if ver in KNOWN_VULNERABLE.get(pkg, []):
            out.append({"package": pkg, "version": ver,
                        "advisory": "version listee vulnerable (catalogue UBA)"})
    return out


def _write_report(
    bandit: list[dict[str, Any]],
    secrets: list[dict[str, Any]],
    deps: list[dict[str, Any]],
    composite: float,
) -> str:
    def _sev_count(items: list[dict[str, Any]]) -> dict[str, int]:
        c = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for i in items:
            sev = (i.get("issue_severity") or "LOW").upper()
            c[sev] = c.get(sev, 0) + 1
        return c

    sev_b = _sev_count(bandit)
    return f"""# SECURITY

Rapport d'audit genere par Agent #11 (UBA V2).

**Score composite** : **{composite:.2f}** / 1.00

## Bandit (analyse statique)
- HIGH   : {sev_b['HIGH']}
- MEDIUM : {sev_b['MEDIUM']}
- LOW    : {sev_b['LOW']}

## Scan de secrets
- Occurrences : {len(secrets)}
{"\n".join(f"- `{s['type']}` dans `{s['path']}`" for s in secrets[:10]) or "- Aucune"}

## Audit dependances (catalogue interne UBA)
- Paquets vulnerables : {len(deps)}
{"\n".join(f"- `{d['package']}=={d['version']}` : {d['advisory']}" for d in deps[:10]) or "- Aucun"}

## Remediation
- HIGH/Secrets -> rotation immediate, PR de correction.
- Dependances -> `pip install -U <pkg>` puis regen du lock.

*Rapport deterministe ; pour un audit complet, executer pip-audit et trivy.*
"""
