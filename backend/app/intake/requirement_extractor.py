"""Upgrade 8 - Extracteur d'exigences : texte brut -> exigences structurees.

Sortie : Requirement[] avec code, label, type (fonctionnel/non-fonctionnel/
conformite/securite/perf), domaine, juridiction, complexite.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.intake.universal_intake import IntakeDocument
from app.orchestration.domain_classifier import DomainReport, classify


@dataclass
class Requirement:
    code: str
    label: str
    type: str       # functional | nonfunctional | compliance | security | performance
    source: str = "spec"
    domain: str = ""
    jurisdiction: str = ""
    complexity: str = "medium"  # low | medium | high
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code, "label": self.label, "type": self.type,
            "source": self.source, "domain": self.domain,
            "jurisdiction": self.jurisdiction, "complexity": self.complexity,
            "evidence": self.evidence[:200],
        }


@dataclass
class ExtractedSpec:
    domain_report: DomainReport
    requirements: list[Requirement] = field(default_factory=list)
    language: str = "fr"
    overall_complexity: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain_report.domain,
            "jurisdiction": self.domain_report.jurisdiction,
            "language": self.language,
            "overall_complexity": self.overall_complexity,
            "requirements_count": len(self.requirements),
            "requirements": [r.to_dict() for r in self.requirements[:50]],
        }


FUNC_HINTS = ("crud", "endpoint", "api", "cree", "liste", "modifie", "supprime",
               "genere", "import", "export", "envoi", "upload", "download")
NON_FUNC_HINTS = ("latence", "performance", "uptime", "sla", "scalab", "disponibilite")
COMPLIANCE_HINTS = ("tva", "tap", "cnas", "irg", "nin", "rgpd", "gdpr", "hipaa", "sox",
                     "conformite", "compliance", "audit")
SECURITY_HINTS = ("jwt", "oauth", "authentif", "autorisation", "rbac", "mfa", "tls",
                   "chiffrement", "secret", "password")
PERF_HINTS = ("rps", "qps", "debit", "throughput", "millisec", "p95", "p99")


def _guess_type(text: str) -> str:
    low = text.lower()
    if any(h in low for h in COMPLIANCE_HINTS):
        return "compliance"
    if any(h in low for h in SECURITY_HINTS):
        return "security"
    if any(h in low for h in PERF_HINTS):
        return "performance"
    if any(h in low for h in NON_FUNC_HINTS):
        return "nonfunctional"
    if any(h in low for h in FUNC_HINTS):
        return "functional"
    return "functional"


def _detect_language(text: str) -> str:
    fr_markers = sum(1 for m in ("le ", "la ", "les ", "une ", "des ", "et ", "que ")
                     if m in text.lower())
    en_markers = sum(1 for m in ("the ", "and ", "for ", "with ", "that ")
                     if m in text.lower())
    return "fr" if fr_markers >= en_markers else "en"


def _complexity(text: str, count_reqs: int) -> str:
    if count_reqs >= 15 or len(text) > 4000:
        return "high"
    if count_reqs >= 5 or len(text) > 1000:
        return "medium"
    return "low"


_BULLET_RE = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)(.+)$", re.MULTILINE)
_SECTION_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


def extract(doc: IntakeDocument) -> ExtractedSpec:
    """Transforme un IntakeDocument en ExtractedSpec."""
    text = doc.text or ""
    dom = classify(text)
    language = _detect_language(text)

    requirements: list[Requirement] = []
    # 1. Chaque puce = une exigence
    for i, m in enumerate(_BULLET_RE.finditer(text), start=1):
        line = m.group(1).strip()
        if len(line) < 8:
            continue
        req_type = _guess_type(line)
        requirements.append(Requirement(
            code=f"REQ_{i:03d}", label=line[:240], type=req_type,
            domain=dom.domain, jurisdiction=dom.jurisdiction,
            complexity="medium", evidence=line,
        ))
    # 2. Sections markdown : "# X" -> exigence generique
    for i, m in enumerate(_SECTION_RE.finditer(text), start=1):
        section = m.group(1).strip()
        if any(section.lower() in r.label.lower() for r in requirements):
            continue
        requirements.append(Requirement(
            code=f"SEC_{i:03d}", label=f"Section: {section}", type="functional",
            source="section_heading", domain=dom.domain, jurisdiction=dom.jurisdiction,
        ))
    # 3. Si rien trouve : 1 exigence globale
    if not requirements:
        requirements.append(Requirement(
            code="REQ_ALL", label=(text[:240] or "Specification"),
            type=_guess_type(text), domain=dom.domain,
            jurisdiction=dom.jurisdiction, evidence=text[:400],
        ))

    return ExtractedSpec(
        domain_report=dom, requirements=requirements,
        language=language,
        overall_complexity=_complexity(text, len(requirements)),
    )
