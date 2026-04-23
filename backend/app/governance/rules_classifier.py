"""V5.2 BLOC 1 - Rules Classifier.

Parcourt l'arbre backend/app/, detecte les constantes (UPPER_CASE) et les
regles en dur (nombres dans le code) puis classifie chaque occurence en
l'une des 4 categories :

  HARDCODED_FROZEN : regles fiscales DZ, lois legales, constantes physiques
  PARAMETRIZABLE   : seuils/timeouts/budgets (BDD system_parameters)
  LEARNABLE        : poids/seuils auto-tuner (BDD avec bounds)
  REASONABLE       : decidable LLM (nommage, architecture)

La classification n'est pas semantique (pas d'IA) : elle utilise des
heuristiques de noms + pattern matching. Le resultat est publie dans
rules_classification_report.md pour revue humaine.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Category = str

CAT_HARDCODED = "HARDCODED_FROZEN"
CAT_PARAMETRIZABLE = "PARAMETRIZABLE"
CAT_LEARNABLE = "LEARNABLE"
CAT_REASONABLE = "REASONABLE"


# Mots-cles qui FORCENT la categorie HARDCODED_FROZEN
HARDCODED_KEYWORDS = [
    "tva", "tap", "cnas", "irg", "ibs", "vefa",
    "nin", "dzd", "dinar", "palier",
    "fiscal", "compliance", "retention",
    "cooling_off", "append_only", "immutable",
    "rls", "tenant_isolation",
    "builder_role", "critic_role", "judge_role",
    "invariant",
]

# Mots-cles PARAMETRIZABLE
PARAMETRIZABLE_KEYWORDS = [
    "threshold", "timeout", "budget", "ttl", "max_iteration",
    "max_retries", "limit", "cap", "rate_limit", "pool_size",
]

# Mots-cles LEARNABLE
LEARNABLE_KEYWORDS = [
    "weight_", "score_weight", "coeff", "prior",
    "pass_min", "cpass_min", "soft_fail_min",
]

# Mots-cles REASONABLE
REASONABLE_KEYWORDS = [
    "template", "prompt_variant", "naming", "pattern",
    "layout", "style", "message", "label",
]


@dataclass
class ClassifiedConstant:
    file: str
    line: int
    name: str
    value_repr: str
    category: Category
    justification: str


def _match_kw(name: str, keywords: list[str]) -> str | None:
    """Cherche une correspondance par token (separateur '_') ou prefix."""
    tokens = [t.lower() for t in re.split(r"[_\s]+", name) if t]
    low = name.lower()
    for kw in keywords:
        kl = kw.rstrip("_").lower()
        if kl in tokens:
            return kw
        # prefix/suffix matches seulement sur tokens, pas substring brut
        for t in tokens:
            if t.startswith(kl) or t.endswith(kl):
                if len(kl) >= 4:  # evite les faux positifs courts
                    return kw
    return None


def _classify_name(name: str, value: Any) -> tuple[Category, str]:
    # HARDCODED mandatory if matches fiscal/legal terms
    hit = _match_kw(name, HARDCODED_KEYWORDS)
    if hit:
        return CAT_HARDCODED, f"token '{hit}' (regle fiscale/legale)"
    hit = _match_kw(name, LEARNABLE_KEYWORDS)
    if hit:
        return CAT_LEARNABLE, f"token '{hit}' (ajustable par auto-tuner)"
    hit = _match_kw(name, PARAMETRIZABLE_KEYWORDS)
    if hit:
        return CAT_PARAMETRIZABLE, f"token '{hit}' (seuil/limite)"
    hit = _match_kw(name, REASONABLE_KEYWORDS)
    if hit:
        return CAT_REASONABLE, f"token '{hit}' (decidable LLM)"
    # Value-based: strings often REASONABLE, numbers often PARAMETRIZABLE
    if isinstance(value, str):
        return CAT_REASONABLE, "chaine libre (probablement texte/template)"
    if isinstance(value, (int, float)):
        return CAT_PARAMETRIZABLE, "numerique sans mot-cle fiscal -> seuil"
    if isinstance(value, (list, tuple)):
        # Paliers/bareme -> hardcoded ; autres liste -> reasonable
        return CAT_PARAMETRIZABLE, "collection numerique -> parametrizable"
    return CAT_REASONABLE, "type ambigu, decidable plus tard"


def scan_file(path: Path) -> list[ClassifiedConstant]:
    """Parse un fichier Python, extrait les constantes UPPER_CASE top-level."""
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except Exception:
        return []
    out: list[ClassifiedConstant] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if not name.isupper() and not re.match(r"^[A-Z_][A-Z0-9_]+$", name):
            continue
        try:
            value = ast.literal_eval(node.value)
        except Exception:
            value = None
        cat, just = _classify_name(name, value)
        out.append(ClassifiedConstant(
            file=str(path), line=node.lineno, name=name,
            value_repr=repr(value)[:120] if value is not None else "<unparsed>",
            category=cat, justification=just,
        ))
    return out


def scan_tree(root: Path) -> list[ClassifiedConstant]:
    """Parcourt tous les *.py sous root."""
    results: list[ClassifiedConstant] = []
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts or "tests" in p.parts:
            continue
        results.extend(scan_file(p))
    return results


def distribution(items: list[ClassifiedConstant]) -> dict[str, int]:
    d: dict[str, int] = {}
    for it in items:
        d[it.category] = d.get(it.category, 0) + 1
    return d


def render_report(items: list[ClassifiedConstant]) -> str:
    dist = distribution(items)
    total = len(items)
    lines: list[str] = [
        "# V5.2 - Rules Classification Report\n",
        f"**Total constantes detectees** : {total}\n",
        "\n## Distribution\n",
    ]
    for cat in (CAT_HARDCODED, CAT_PARAMETRIZABLE, CAT_LEARNABLE, CAT_REASONABLE):
        n = dist.get(cat, 0)
        pct = (n / total * 100) if total else 0
        lines.append(f"- **{cat}** : {n} ({pct:.1f}%)\n")
    # Grouped by category
    for cat in (CAT_HARDCODED, CAT_PARAMETRIZABLE, CAT_LEARNABLE, CAT_REASONABLE):
        cat_items = [i for i in items if i.category == cat]
        if not cat_items:
            continue
        lines.append(f"\n## {cat} ({len(cat_items)} items)\n")
        lines.append("| File | Line | Constant | Value | Justification |\n")
        lines.append("|---|---|---|---|---|\n")
        for it in sorted(cat_items, key=lambda x: (x.file, x.line))[:80]:
            # Short file path
            short = it.file.replace("\\", "/").split("backend/")[-1]
            lines.append(f"| {short} | {it.line} | `{it.name}` | "
                          f"`{it.value_repr[:60]}` | {it.justification} |\n")
        if len(cat_items) > 80:
            lines.append(f"\n_(+{len(cat_items)-80} autres)_\n")
    return "".join(lines)
