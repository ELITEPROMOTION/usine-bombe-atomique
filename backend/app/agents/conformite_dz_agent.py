"""Agent #18 Conformite Algerie - moteur deterministe.

Verifie les regles de conformite fiscales et reglementaires algeriennes
pertinentes pour un livrable back-end :

  R1. TVA 19 %    -> constante 0.19 ou '19' + mot TVA presents
  R2. TAP 2 %     -> constante 0.02 ou '2%' + mot TAP presents
  R3. IRG         -> presence d'un bareme progressif si paie (tranches 30k+)
  R4. CNAS 9%/26% -> si domaine paie/RH : 0.09 et 0.26 presents
  R5. NIN 18 chiffres -> validator present si entites nominatives
  R6. Devise DZD  -> 'DZD' ou 'Dinar' mentionne
  R7. Pas de regulations non-DZ (GDPR acceptable ; SOX/HIPAA -> alerte)

Chaque regle est OPTIONNELLE ou OBLIGATOIRE selon le contexte (detecte a
partir des mots-cles dans la spec). Score = regles passees / regles applicables.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.workspace import Workspace


@dataclass
class RuleResult:
    rule: str
    label: str
    applicable: bool
    passed: bool
    evidence: list[str] = field(default_factory=list)


class ConformiteDzAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="agent-18-conformite-dz",
                         name="Conformite DZ", version="1.0.0")
        self.category = "compliance"

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        workspace: Workspace = inputs["workspace"]
        spec: str = inputs.get("spec", "")
        manifest = inputs.get("manifest") or workspace.manifest()

        corpus = _read_corpus(workspace, manifest)
        spec_low = spec.lower()
        is_paie = any(w in spec_low for w in ("paie", "salaire", "rh", "cnas", "irg"))
        is_vefa = any(w in spec_low for w in ("vefa", "residence", "immobilier", "promotion"))
        is_person = any(w in spec_low for w in ("client", "employe", "utilisateur", "nin", "personne"))

        rules: list[RuleResult] = [
            _rule_tva(corpus),
            _rule_tap(corpus),
            _rule_cnas(corpus, applicable=is_paie),
            _rule_irg(corpus, applicable=is_paie),
            _rule_nin(corpus, applicable=is_person),
            _rule_devise(corpus),
            _rule_no_foreign_regs(corpus),
            _rule_vefa_paliers(corpus, applicable=is_vefa),
        ]

        applicable = [r for r in rules if r.applicable]
        passed = [r for r in applicable if r.passed]
        score = len(passed) / max(1, len(applicable))

        return {
            "score": round(score, 3),
            "passed": score >= 0.85,
            "domain": {"paie": is_paie, "vefa": is_vefa, "persons": is_person},
            "rules": [
                {
                    "rule": r.rule, "label": r.label,
                    "applicable": r.applicable, "passed": r.passed,
                    "evidence": r.evidence[:3],
                } for r in rules
            ],
            "summary": f"{len(passed)}/{len(applicable)} regles applicables passees",
        }


def _read_corpus(ws: Workspace, manifest: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for m in manifest:
        path = str(m.get("path", ""))
        if path.endswith((".py", ".md", ".txt", ".yaml", ".yml", ".json")):
            try:
                chunks.append(ws.read(path))
            except FileNotFoundError:
                continue
    return "\n".join(chunks)


def _find(corpus: str, pattern: str | re.Pattern[str], limit: int = 3) -> list[str]:
    pat = re.compile(pattern) if isinstance(pattern, str) else pattern
    return [m.group(0) for m in list(pat.finditer(corpus))[:limit]]


def _rule_tva(corpus: str) -> RuleResult:
    tva_word = re.search(r"\bTVA\b", corpus)
    pct = re.search(r"\b0\.19\b|\b19\s*%", corpus)
    ok = bool(tva_word and pct)
    ev = _find(corpus, r"\bTVA\b[^\n]{0,80}") + _find(corpus, r"\b0\.19\b|\b19\s*%")
    return RuleResult("R1_TVA19", "TVA 19% citee + constante presente", True, ok, ev)


def _rule_tap(corpus: str) -> RuleResult:
    tap_word = re.search(r"\bTAP\b", corpus)
    pct = re.search(r"\b0\.02\b|\b2\s*%", corpus)
    ok = bool(tap_word and pct)
    ev = _find(corpus, r"\bTAP\b[^\n]{0,80}")
    return RuleResult("R2_TAP2", "TAP 2% citee + constante presente", True, ok, ev)


def _rule_cnas(corpus: str, applicable: bool) -> RuleResult:
    ok = applicable and bool(
        re.search(r"\b0\.09\b|\b9\s*%", corpus)
        and re.search(r"\b0\.26\b|\b26\s*%", corpus)
    )
    ev = _find(corpus, r"cnas[^\n]{0,80}", limit=3)
    return RuleResult("R3_CNAS", "CNAS 9% salarie + 26% employeur",
                      applicable, ok, ev)


def _rule_irg(corpus: str, applicable: bool) -> RuleResult:
    # IRG progressif : detection de plusieurs tranches (>=3 seuils de montants)
    nums = re.findall(r"(?:\s|>=|<=|>|<)\s*(\d{4,7})", corpus)
    ok = applicable and (re.search(r"\bIRG\b", corpus) is not None) and len(set(nums)) >= 3
    ev = _find(corpus, r"IRG[^\n]{0,80}", limit=3)
    return RuleResult("R4_IRG", "IRG progressif (>=3 tranches)",
                      applicable, ok, ev)


def _rule_nin(corpus: str, applicable: bool) -> RuleResult:
    ok = applicable and bool(
        re.search(r"nin", corpus, re.IGNORECASE)
        and (re.search(r"\b18\b", corpus) or re.search(r"\{18\}", corpus))
    )
    ev = _find(corpus, r"nin[^\n]{0,80}", limit=3)
    return RuleResult("R5_NIN18", "NIN 18 chiffres valide", applicable, ok, ev)


def _rule_devise(corpus: str) -> RuleResult:
    ok = bool(re.search(r"\bDZD\b|\bDinar|Dinars", corpus, re.IGNORECASE))
    ev = _find(corpus, r"\bDZD\b|\bDinar")
    return RuleResult("R6_DZD", "Devise DZD / Dinar mentionnee", True, ok, ev)


def _rule_no_foreign_regs(corpus: str) -> RuleResult:
    forbidden = re.findall(r"\b(SOX|HIPAA|CCPA|PCI[- ]DSS)\b", corpus, re.IGNORECASE)
    ok = len(forbidden) == 0
    return RuleResult("R7_NoForeignRegs",
                      "Pas de regulations non pertinentes (SOX/HIPAA/CCPA)",
                      True, ok, list(set(forbidden))[:3])


def _rule_vefa_paliers(corpus: str, applicable: bool) -> RuleResult:
    ok = applicable and all(
        re.search(pat, corpus) for pat in (r"\b20\b", r"\b15\b", r"\b35\b", r"\b25\b", r"\b5\b")
    )
    ev = _find(corpus, r"palier[^\n]{0,80}", limit=2)
    return RuleResult("R8_VEFA_Paliers", "Paliers VEFA 20/15/35/25/5 presents",
                      applicable, ok, ev)
