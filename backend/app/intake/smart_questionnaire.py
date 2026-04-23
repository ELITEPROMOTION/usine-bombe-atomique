"""Upgrade 10 - Questionnaire intelligent : pourquoi + suggestion + options.

Genere une liste de questions ciblees depuis un AmbiguityReport. Chaque
question contient :
- id, question, pourquoi, type (choice|free|file|number),
  suggested_answer, options, criticality (low|medium|high|critical),
  impact_if_skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.intake.ambiguity_detector import AmbiguityReport


@dataclass
class Question:
    id: str
    question: str
    pourquoi: str
    type: str = "free"
    suggested_answer: str = ""
    options: list[str] = field(default_factory=list)
    criticality: str = "medium"
    impact_if_skipped: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "question": self.question,
            "pourquoi": self.pourquoi, "type": self.type,
            "suggested_answer": self.suggested_answer, "options": self.options,
            "criticality": self.criticality,
            "impact_if_skipped": self.impact_if_skipped,
        }


_ASPECT_QUESTIONS = {
    "target_platform": Question(
        id="Q_PLATFORM",
        question="Quelle plateforme cible pour le deploiement ?",
        pourquoi="Determine l'infra generee (Docker local, AWS ECS, Kubernetes).",
        type="choice", options=["Docker local", "AWS", "Kubernetes", "Vercel", "Autre"],
        suggested_answer="Docker local", criticality="high",
        impact_if_skipped="Infrastructure par defaut (Docker) qui ne correspondra peut-etre pas.",
    ),
    "language_stack": Question(
        id="Q_STACK",
        question="Quelle stack / langage preferer ?",
        pourquoi="Oriente la generation du code et le choix d'agents.",
        type="choice", options=["Python/FastAPI", "Node/TypeScript", "Java/Spring", "Go"],
        suggested_answer="Python/FastAPI", criticality="high",
        impact_if_skipped="Par defaut Python/FastAPI.",
    ),
    "data_volume": Question(
        id="Q_DATA_VOLUME",
        question="Volume de donnees attendu (utilisateurs / lignes) ?",
        pourquoi="Dimensionnement de la BDD, strategie d'indexation, cache.",
        type="free", suggested_answer="< 10 000 lignes / mois",
        criticality="medium",
        impact_if_skipped="Hypothese sous-dimensionnee possible.",
    ),
    "sla": Question(
        id="Q_SLA",
        question="Quel SLA de disponibilite vise (uptime, latence p95) ?",
        pourquoi="Determine tests de charge, tolerance aux pannes, redondance.",
        type="free", suggested_answer="uptime 99.5%, p95 < 500ms",
        criticality="medium",
        impact_if_skipped="Pas de gate de performance, risque en prod.",
    ),
    "auth": Question(
        id="Q_AUTH",
        question="Quelle authentification (JWT, OAuth, SSO) ?",
        pourquoi="Choix critique pour la securite et les integrations.",
        type="choice", options=["JWT local", "OAuth2 (Google/GitHub)", "SSO entreprise", "Aucune"],
        suggested_answer="JWT local", criticality="high",
        impact_if_skipped="Auth JWT par defaut, pas d'integration SSO.",
    ),
}


def build(report: AmbiguityReport) -> list[Question]:
    """Construit la liste de questions a partir des ambiguites detectees."""
    questions: list[Question] = []

    # Contradictions : UNE question par contradiction (bloquante)
    for c in report.contradictions:
        questions.append(Question(
            id=f"Q_CONTRA_{c.rule.upper()}",
            question=(f"Contradiction detectee : '{c.side_a}' s'oppose a '{c.side_b}'. "
                      "Laquelle est correcte ?"),
            pourquoi=f"Regle {c.rule} : impossible de livrer sans resoudre.",
            type="free", options=[c.side_a, c.side_b],
            criticality="critical",
            impact_if_skipped="Livraison bloquee, verdict HARD_FAIL automatique.",
        ))

    # Aspects manquants : question dediee
    for asp in report.missing_aspects:
        if asp in _ASPECT_QUESTIONS:
            questions.append(_ASPECT_QUESTIONS[asp])

    # Hypotheses risquees : confirmation
    for assumption in report.risky_assumptions:
        questions.append(Question(
            id=f"Q_RISK_{len(questions)}",
            question=f"Confirmez-vous : {assumption} ?",
            pourquoi="Le systeme prefere demander plutot que supposer silencieusement.",
            type="choice", options=["Oui, c'est acceptable", "Non, ajouter la contrainte"],
            criticality="medium",
            impact_if_skipped="Hypothese acceptee par defaut, logguee comme risque.",
        ))

    # Enonces vagues : UNE question agregee (pas une par vague)
    if report.vague_statements:
        questions.append(Question(
            id="Q_VAGUE_AGG",
            question=(f"{len(report.vague_statements)} enonce(s) vague(s) detectes. "
                      "Pouvez-vous les preciser ?"),
            pourquoi="Les termes vagues deviennent souvent des bugs silencieux.",
            type="free", suggested_answer="",
            criticality="medium",
            impact_if_skipped="Interpretation par defaut, risque de derive du scope.",
        ))

    return questions


def to_payload(questions: list[Question]) -> dict[str, Any]:
    return {
        "questions_count": len(questions),
        "has_blocking": any(q.criticality == "critical" for q in questions),
        "questions": [q.to_dict() for q in questions],
    }
