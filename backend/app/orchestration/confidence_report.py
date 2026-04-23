"""Per-artifact Confidence Report V4.1 - assertions classees.

Chaque artefact genere produit une liste d'assertions (ex: "les endpoints
retournent du JSON valide", "aucun secret hardcode", "la fonction X
implemente la TVA a 19%"). Chaque assertion est classee :

- prouvee        : verification deterministe reussie (AST / test / regex)
- probable       : heuristique plausible mais non verifiee mecaniquement
- non_prouvee    : demande une preuve qui manque (=> bloquer si critique)
- contradictoire : verification contredit l'assertion

Si au moins une assertion `critical` est `non_prouvee` ou `contradictoire`,
le rapport renvoie `block=True`.
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

AssertionStatus = Literal["prouvee", "probable", "non_prouvee", "contradictoire"]


@dataclass
class Assertion:
    label: str
    status: AssertionStatus
    critical: bool = False
    evidence: str = ""


@dataclass
class ArtifactConfidence:
    path: str
    assertions: list[Assertion] = field(default_factory=list)
    block: bool = False
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "block": self.block,
            "summary": self.summary,
            "assertions": [
                {"label": a.label, "status": a.status,
                 "critical": a.critical, "evidence": a.evidence[:200]}
                for a in self.assertions
            ],
        }


_SECRET_RE = re.compile(
    r"(?i)(password|secret|api_key|token)\s*=\s*['\"][^'\"]{6,}['\"]",
)
_ENDPOINT_RE = re.compile(r"@(?:router|app)\.(get|post|put|delete|patch)\(")


def _assert_syntax(content: str) -> tuple[Assertion, ast.Module | None]:
    try:
        tree = ast.parse(content)
        return Assertion("syntaxe Python valide", "prouvee", critical=True,
                          evidence="ast.parse OK"), tree
    except SyntaxError as exc:
        return Assertion("syntaxe Python valide", "contradictoire", critical=True,
                          evidence=f"SyntaxError line {exc.lineno}: {exc.msg}"), None


def _assert_no_secret(content: str) -> Assertion:
    hits = [m.group(0) for m in _SECRET_RE.finditer(content)
            if "changeme" not in m.group(0).lower()]
    if hits:
        return Assertion("aucun secret hardcode", "contradictoire", critical=True,
                          evidence=f"Match: {hits[0][:80]}")
    return Assertion("aucun secret hardcode", "prouvee", critical=True,
                      evidence="regex secret scan clean")


def _assert_response_model(content: str) -> Assertion | None:
    if not _ENDPOINT_RE.search(content):
        return None
    has_rm = "response_model=" in content
    return Assertion(
        "endpoints typees (response_model)",
        "prouvee" if has_rm else "non_prouvee", critical=False,
        evidence="response_model present" if has_rm else "aucun response_model detecte",
    )


def _assert_module_doc(tree: ast.Module) -> Assertion:
    has = ast.get_docstring(tree) is not None
    return Assertion("docstring module", "prouvee" if has else "probable",
                      critical=False,
                      evidence="ast.get_docstring" if has else "heuristique")


def _assert_no_print(content: str, path: str) -> Assertion | None:
    if "tests/" in path:
        return None
    has_print = bool(re.search(r"^\s*print\(", content, re.M))
    return Assertion("pas de print() en prod",
                      "contradictoire" if has_print else "prouvee",
                      critical=False,
                      evidence="print() detecte" if has_print else "regex clean")


def _classify_python_artifact(path: str, content: str) -> ArtifactConfidence:
    rep = ArtifactConfidence(path=path)
    syntax_assert, tree = _assert_syntax(content)
    rep.assertions.append(syntax_assert)
    if tree is None:
        rep.block = True
        rep.summary = "Syntaxe invalide, blocage."
        return rep

    rep.assertions.append(_assert_no_secret(content))
    rm = _assert_response_model(content)
    if rm is not None:
        rep.assertions.append(rm)
    rep.assertions.append(_assert_module_doc(tree))
    np_ = _assert_no_print(content, path)
    if np_ is not None:
        rep.assertions.append(np_)

    critical_issues = [a for a in rep.assertions
                       if a.critical and a.status in ("non_prouvee", "contradictoire")]
    if critical_issues:
        rep.block = True
        rep.summary = f"{len(critical_issues)} assertion(s) critique(s) non prouvee(s)."
    else:
        rep.summary = f"{len(rep.assertions)} assertions analysees, block=False."
    return rep


def classify_artifact(path: str, content: str) -> ArtifactConfidence:
    """Classifie les assertions d'un artefact donne (auto-detecte le type)."""
    if path.endswith(".py"):
        return _classify_python_artifact(path, content)
    # Type non supporte : toutes probable
    rep = ArtifactConfidence(path=path)
    rep.assertions.append(Assertion(
        f"type {path.rsplit('.', 1)[-1]} non analyse en detail",
        "probable", critical=False,
        evidence="non-python : heuristique seule",
    ))
    rep.summary = "Type non-Python, pas de blocage."
    return rep


def classify_manifest(
    workspace: Any,
    manifest: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rapport global : classification par artefact + verdict consolide."""
    reports: list[ArtifactConfidence] = []
    for meta in manifest:
        path = str(meta.get("path", ""))
        try:
            content = workspace.read(path)
        except FileNotFoundError:
            continue
        reports.append(classify_artifact(path, content))

    block_overall = any(r.block for r in reports)
    total_assertions = sum(len(r.assertions) for r in reports)
    proven = sum(1 for r in reports for a in r.assertions if a.status == "prouvee")
    contradictory = sum(1 for r in reports for a in r.assertions
                        if a.status == "contradictoire")
    return {
        "block": block_overall,
        "artifacts_analyzed": len(reports),
        "assertions_total": total_assertions,
        "assertions_proven": proven,
        "assertions_contradictory": contradictory,
        "ratio_proven": round(proven / max(1, total_assertions), 3),
        "reports": [r.to_dict() for r in reports[:20]],  # on tronque pour eviter payload gigantesque
    }
