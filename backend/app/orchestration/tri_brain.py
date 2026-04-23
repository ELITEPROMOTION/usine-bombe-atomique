"""Tri-Cerveau - Builder / Critic / Judge (CDC Ch.9 V2).

Principe :
- **Builder** produit le livrable (code) a partir de la specification.
- **Critic** inspecte le livrable et liste les defauts (severite + categorie).
- **Judge** decide : APPROVE / REFINE / REJECT selon un bareme deterministe.
- Si REFINE : un unique round de raffinement (Builder re-appele avec la critique
  en contexte), puis nouvelle critique, nouveau verdict.

Les 3 roles utilisent le LLM quand une cle ANTHROPIC_API_KEY est disponible
sinon un fallback deterministe base sur AST + heuristiques.

Entree : `BuilderFn` retournant un dict {path: content}.
Sortie : `TriBrainReport` + ecriture des fichiers finaux dans le workspace.
"""
from __future__ import annotations

import ast
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agents.workspace import Workspace
from app.config import get_settings

logger = logging.getLogger(__name__)

Verdict = Literal["approve", "refine", "reject"]
Severity = Literal["critical", "major", "minor", "info"]

BuilderFn = Callable[[str, list["CriticIssue"] | None], Awaitable[dict[str, str]]]


@dataclass
class CriticIssue:
    severity: Severity
    category: str  # "syntax" | "security" | "quality" | "conformity" | "architecture"
    message: str
    path: str | None = None


@dataclass
class JudgeDecision:
    verdict: Verdict
    critical_count: int
    major_count: int
    minor_count: int
    rationale: str


@dataclass
class TriBrainReport:
    files_count: int
    rounds: int
    final_verdict: Verdict
    builder_source: str
    critic_issues: list[CriticIssue] = field(default_factory=list)
    judge_history: list[JudgeDecision] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Orchestration principale
# ---------------------------------------------------------------------------

async def run_tri_brain(
    spec: str,
    workspace: Workspace,
    builder: BuilderFn,
    max_rounds: int = 1,
) -> TriBrainReport:
    """Pipeline Builder/Critic/Judge avec au plus `max_rounds` raffinements."""
    rounds = 0
    critic_issues: list[CriticIssue] = []
    judge_history: list[JudgeDecision] = []
    files: dict[str, str] = {}
    builder_source = "unknown"

    while True:
        # -- Build --
        files = await builder(spec, critic_issues or None)
        builder_source = _detect_builder_source(files)

        # -- Critic --
        critic_issues = await _critic(spec, files)

        # -- Judge --
        decision = _judge(critic_issues)
        judge_history.append(decision)
        logger.info(
            "tri_brain round=%d verdict=%s critical=%d major=%d minor=%d",
            rounds, decision.verdict, decision.critical_count,
            decision.major_count, decision.minor_count,
        )

        if decision.verdict != "refine" or rounds >= max_rounds:
            break
        rounds += 1

    # Ecriture finale
    for path, content in files.items():
        workspace.write(path, content)

    return TriBrainReport(
        files_count=len(files),
        rounds=rounds,
        final_verdict=judge_history[-1].verdict,
        builder_source=builder_source,
        critic_issues=critic_issues,
        judge_history=judge_history,
    )


def _detect_builder_source(files: dict[str, str]) -> str:
    """Heuristique : taille + diversite -> LLM ou template."""
    if not files:
        return "empty"
    avg_len = sum(len(c) for c in files.values()) / len(files)
    return "llm" if avg_len > 500 and len(files) > 6 else "template"


# ---------------------------------------------------------------------------
# Critic
# ---------------------------------------------------------------------------

CRITIC_SYSTEM = """Tu es un reviewer senior. On te donne une liste de fichiers produits par un autre agent.
Retourne UNIQUEMENT un JSON {"issues": [{"severity": "critical|major|minor|info",
"category": "syntax|security|quality|conformity|architecture", "message": "...", "path": "..."}]}.
Severity critical = bloquant (syntax, secret hardcode, injection). Major = test manquant, endpoint sans validation.
Minor = style, nommage. Sois concis, max 20 issues."""


async def _critic(spec: str, files: dict[str, str]) -> list[CriticIssue]:
    """Critic : LLM si possible, sinon heuristiques deterministes."""
    settings = get_settings()
    issues: list[CriticIssue] = []

    # --- Couche deterministe (toujours appliquee) ---
    issues.extend(_deterministic_critic(files))

    # --- Couche LLM (optionnelle, en plus) ---
    if settings.ANTHROPIC_API_KEY and len(files) <= 30:
        try:
            issues.extend(await _llm_critic(spec, files, settings))
        except Exception as exc:
            logger.warning("LLM critic failed, deterministic-only: %s", exc)

    # Dedup naif (message+path)
    seen: set[tuple[str, str]] = set()
    uniq: list[CriticIssue] = []
    for it in issues:
        key = (it.message[:80], it.path or "")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq[:40]


_HARDCODED_CRED_RE = re.compile(
    r"(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]{6,}['\"]",
)
_PRINT_RE = re.compile(r"^\s*print\(", re.M)
_ENDPOINT_RE = re.compile(r"@(?:router|app)\.(get|post|put|delete|patch)\(")


def _critic_python_file(path: str, content: str) -> list[CriticIssue]:
    """Inspecte un fichier .py et retourne les issues deterministes."""
    try:
        ast.parse(content)
    except SyntaxError as exc:
        return [CriticIssue("critical", "syntax",
                            f"SyntaxError: {exc.msg} line {exc.lineno}", path)]

    out: list[CriticIssue] = []
    if _HARDCODED_CRED_RE.search(content) and "changeme" not in content.lower():
        out.append(CriticIssue("critical", "security",
                               "Possible hardcoded credential", path))
    if _PRINT_RE.search(content) and "tests/" not in path:
        out.append(CriticIssue("minor", "quality",
                               "print() en code de prod; preferer logging", path))
    if path.startswith("app/") and not content.lstrip().startswith(('"""', "'''")):
        out.append(CriticIssue("minor", "quality",
                               "Module sans docstring d'introduction", path))
    if _ENDPOINT_RE.search(content) and "response_model=" not in content:
        out.append(CriticIssue("major", "quality",
                               "Endpoint(s) sans response_model", path))
    return out


def _critic_structural(files: dict[str, str]) -> list[CriticIssue]:
    """Controle presence des fichiers structurels (main, reqs, tests)."""
    names = set(files.keys())
    out: list[CriticIssue] = []
    if not any(p.endswith("main.py") for p in names):
        out.append(CriticIssue("critical", "architecture", "main.py manquant", None))
    if not any(p == "requirements.txt" for p in names):
        out.append(CriticIssue("major", "architecture", "requirements.txt manquant", None))
    if not any(p.startswith("tests/") for p in names):
        out.append(CriticIssue("major", "quality", "Aucun fichier de test", None))
    return out


def _deterministic_critic(files: dict[str, str]) -> list[CriticIssue]:
    """Critic deterministe (AST + regex) sur l'ensemble des fichiers."""
    out: list[CriticIssue] = []
    for path, content in files.items():
        if path.endswith(".py"):
            out.extend(_critic_python_file(path, content))
    out.extend(_critic_structural(files))
    return out


async def _llm_critic(spec: str, files: dict[str, str], settings: Any) -> list[CriticIssue]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    summary = {p: _excerpt(c) for p, c in files.items()}
    prompt = (
        f"Specification:\n{spec[:2000]}\n\n"
        f"Fichiers produits (extraits):\n{json.dumps(summary, ensure_ascii=False)[:6000]}"
    )
    msg = await client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=1500,
        system=CRITIC_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    from anthropic.types import TextBlock
    text = "".join(b.text for b in msg.content if isinstance(b, TextBlock))
    try:
        payload = _extract_json(text)
    except Exception:
        return []
    raw = payload.get("issues", [])
    result: list[CriticIssue] = []
    for it in raw if isinstance(raw, list) else []:
        if not isinstance(it, dict):
            continue
        sev = str(it.get("severity", "minor"))
        if sev not in ("critical", "major", "minor", "info"):
            sev = "minor"
        result.append(CriticIssue(
            severity=sev,  # type: ignore[arg-type]
            category=str(it.get("category", "quality")),
            message=str(it.get("message", ""))[:200],
            path=it.get("path"),
        ))
    return result


def _excerpt(content: str, max_chars: int = 600) -> str:
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + f"\n... [+{len(content) - max_chars} chars]"


def _extract_json(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

def _judge(issues: list[CriticIssue]) -> JudgeDecision:
    critical = sum(1 for i in issues if i.severity == "critical")
    major = sum(1 for i in issues if i.severity == "major")
    minor = sum(1 for i in issues if i.severity == "minor")

    if critical >= 1:
        return JudgeDecision("reject", critical, major, minor,
                             f"{critical} issue(s) critique(s) -> rejet")
    if major >= 3:
        return JudgeDecision("refine", critical, major, minor,
                             f"{major} issues majeures -> raffinement demande")
    return JudgeDecision("approve", critical, major, minor,
                         "Livrable accepte : aucune issue critique, majeures sous seuil")
