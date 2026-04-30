"""Moteur de qualification : analyse d'un CDC client par Claude.

Le moteur ne fait PAS lui-meme l'appel reel a l'API Claude — il delegue a
un `ClaudeProvider` (Protocol). Ce provider est :

- en Phase 9C : `StubClaudeProvider` (donnees canoniques pour les tests)
- en Phase 9D : un vrai client routes via l'AI Router (Phase 9D)

Le contrat Claude (system prompt + JSON schema attendu) est defini ici
pour rester un point d'entree unique : on peut changer de moteur LLM sans
toucher au reste du code.
"""
from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field, ValidationError

from app.saas_factory.intelligence.packs.catalog import PackCatalog
from app.saas_factory.intelligence.pricing_engine import ProjectFacets

logger = logging.getLogger(__name__)


class QualificationConfidence(str, enum.Enum):
    HIGH = "high"      # CDC tres clair, peu d'ambiguite
    MEDIUM = "medium"  # quelques zones grises
    LOW = "low"        # ambigu, devrait etre escalade


class _ClaudeResponseSchema(BaseModel):
    """Format strict que le Claude provider doit retourner (apres parsing)."""
    pack_hint: str
    facets: ProjectFacets
    detected_domain: str = Field(min_length=1, max_length=100)
    detected_locales: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confidence: QualificationConfidence
    rationale: str = Field(min_length=1, max_length=2000)


SYSTEM_PROMPT = """Tu es un analyste senior CDC (cahier des charges) pour
UBA Studio Platform. A partir d'un CDC client, tu produis un JSON strict
avec ces cles :

{
  "pack_hint": "ecommerce_small|ecommerce_medium|ecommerce_large|saas_small|saas_medium|saas_large|mobile_app|api_b2b|custom",
  "facets": {
    "complexity": 0..10, "domain_specialty": 0..10, "urgency": 0..10,
    "support_level": 0..10, "compliance_overhead": 0..10,
    "i18n_locales": 0..10, "integration_count": 0..20,
    "design_intensity": 0..10, "data_migration": 0..10,
    "training_included": 0..10, "sla_tier": 0..3, "scaling_factor": 0..10,
    "geographic_spread": 0..5, "audit_required": 0..3,
    "post_launch_window": 0..12
  },
  "detected_domain": "string",
  "detected_locales": ["en","fr",...],
  "risks": ["string", ...],
  "confidence": "high|medium|low",
  "rationale": "string explaining the choices"
}

Regles strictes :
- Si le CDC mentionne explicitement une demande "sur-mesure non standard",
  pack_hint = "custom".
- 'urgency' >= 7 => mentionne dans 'risks'.
- 'compliance_overhead' >= 5 si secteur sante/banque/public.
- 'rationale' explique en 3-6 phrases pourquoi ces choix.
"""


class ClaudeProvider(Protocol):
    """Interface attendue du provider Claude (ou tout LLM equivalent)."""

    async def analyze_cdc(
        self,
        *,
        cdc_text: str,
        system_prompt: str,
        max_tokens: int = 2000,
    ) -> dict[str, Any]: ...


class StubClaudeProvider:
    """Provider de test : retourne une reponse canonique determine.

    L'idee : tu lui passes une reponse a renvoyer ; tous les appels la rendent.
    En production reelle on injecte un provider qui parle a l'API Claude.
    """

    def __init__(self, canned_response: dict[str, Any]) -> None:
        self._response = canned_response
        self.call_count = 0

    async def analyze_cdc(
        self,
        *,
        cdc_text: str,
        system_prompt: str,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        self.call_count += 1
        # Sanity : on n'utilise pas `assert` (saute en mode -O).
        if not system_prompt:
            raise ValueError("system_prompt vide")
        if not cdc_text:
            raise ValueError("cdc_text vide")
        return dict(self._response)


@dataclass(frozen=True)
class Qualification:
    qualification_id: UUID
    project_id: str
    pack_hint: str
    facets: ProjectFacets
    detected_domain: str
    detected_locales: tuple[str, ...]
    risks: tuple[str, ...]
    confidence: QualificationConfidence
    rationale: str
    cdc_text_hash: str
    created_at: datetime


class QualificationError(RuntimeError):
    pass


def _hash_cdc(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class QualificationEngine:
    def __init__(
        self,
        pool: asyncpg.Pool,
        pack_catalog: PackCatalog,
        provider: ClaudeProvider,
    ) -> None:
        self._pool = pool
        self._packs = pack_catalog
        self._provider = provider

    async def qualify(
        self,
        *,
        project_id: str,
        cdc_text: str,
        max_tokens: int = 2000,
    ) -> Qualification:
        if not cdc_text.strip():
            raise QualificationError("cdc_text vide")

        raw = await self._provider.analyze_cdc(
            cdc_text=cdc_text,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=max_tokens,
        )
        try:
            parsed = _ClaudeResponseSchema.model_validate(raw)
        except ValidationError as exc:
            raise QualificationError(
                f"reponse provider invalide: {exc}"
            ) from exc

        if not self._packs.has(parsed.pack_hint):
            raise QualificationError(
                f"pack_hint inconnu du catalogue: {parsed.pack_hint!r}"
            )

        cdc_hash = _hash_cdc(cdc_text)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO intelligence_qualifications (
                    project_id, pack_hint, facets_json, detected_domain,
                    detected_locales, risks, confidence, rationale,
                    cdc_text_hash
                ) VALUES (
                    $1, $2, $3::jsonb, $4, $5, $6, $7, $8, $9
                ) RETURNING qualification_id, created_at
                """,
                project_id,
                parsed.pack_hint,
                json.dumps(parsed.facets.as_dict(), sort_keys=True),
                parsed.detected_domain,
                list(parsed.detected_locales),
                list(parsed.risks),
                parsed.confidence.value,
                parsed.rationale,
                cdc_hash,
            )

        logger.info(
            "qualification.done project=%s pack_hint=%s confidence=%s",
            project_id, parsed.pack_hint, parsed.confidence.value,
        )

        return Qualification(
            qualification_id=row["qualification_id"],
            project_id=project_id,
            pack_hint=parsed.pack_hint,
            facets=parsed.facets,
            detected_domain=parsed.detected_domain,
            detected_locales=tuple(parsed.detected_locales),
            risks=tuple(parsed.risks),
            confidence=parsed.confidence,
            rationale=parsed.rationale,
            cdc_text_hash=cdc_hash,
            created_at=row["created_at"],
        )
