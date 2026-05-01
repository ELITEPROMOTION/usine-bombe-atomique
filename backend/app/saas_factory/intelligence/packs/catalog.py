"""Chargement et validation du catalogue de packs (9 packs V9).

Le fichier `packs.json` est valide via Pydantic v2 a l'import. Chaque pack
declare son prix de base, ses modules, ses livrables, ses phases ponderees
(somme = 100%), et un drapeau `manual_quote_required` pour le pack `custom`
qui sort du flux automatique.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

DEFAULT_PACKS_PATH: Final[Path] = Path(__file__).parent / "packs.json"

PackId = Literal[
    "ecommerce_small", "ecommerce_medium", "ecommerce_large",
    "saas_small", "saas_medium", "saas_large",
    "mobile_app", "api_b2b", "custom",
]


class PackCatalogError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Pydantic models (validation)
# ---------------------------------------------------------------------------
class _PhaseWeightsModel(BaseModel):
    ANALYSIS: int = Field(ge=1, le=50)
    DESIGN: int = Field(ge=1, le=50)
    CORE: int = Field(ge=1, le=60)
    FEATURES: int = Field(ge=1, le=50)
    TESTING: int = Field(ge=1, le=30)
    DEPLOY: int = Field(ge=1, le=30)

    @model_validator(mode="after")
    def _sum_to_100(self) -> _PhaseWeightsModel:
        total = (
            self.ANALYSIS + self.DESIGN + self.CORE
            + self.FEATURES + self.TESTING + self.DEPLOY
        )
        if total != 100:
            raise ValueError(f"phases doit sommer a 100 (actuel: {total})")
        return self


class _PackDefinitionModel(BaseModel):
    label_i18n: dict[str, str]
    base_price_eur: int = Field(ge=0)
    estimated_cost_eur: int = Field(ge=0)
    max_complexity_factor: float = Field(ge=1.0, le=5.0)
    base_modules: list[str]
    base_deliverables: list[str]
    suggested_addons: list[str]
    phases: _PhaseWeightsModel
    manual_quote_required: bool

    @field_validator("label_i18n")
    @classmethod
    def _label_has_en_fr(cls, v: dict[str, str]) -> dict[str, str]:
        if "en" not in v or "fr" not in v:
            raise ValueError("label_i18n doit contenir 'en' et 'fr'")
        return v

    @model_validator(mode="after")
    def _custom_pack_is_zero(self) -> _PackDefinitionModel:
        # Si manual_quote_required, le base_price doit etre 0 (sinon
        # l'auto-pricing pourrait le voler).
        if self.manual_quote_required and self.base_price_eur != 0:
            raise ValueError(
                "manual_quote_required=true exige base_price_eur=0"
            )
        return self


class _PacksFileModel(BaseModel):
    version: str
    packs: dict[str, _PackDefinitionModel]


# ---------------------------------------------------------------------------
# Runtime models (frozen dataclasses)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PhaseWeights:
    ANALYSIS: int
    DESIGN: int
    CORE: int
    FEATURES: int
    TESTING: int
    DEPLOY: int

    @property
    def total(self) -> int:
        return (
            self.ANALYSIS + self.DESIGN + self.CORE
            + self.FEATURES + self.TESTING + self.DEPLOY
        )

    def as_ordered_pairs(self) -> tuple[tuple[str, int], ...]:
        return (
            ("ANALYSIS", self.ANALYSIS),
            ("DESIGN", self.DESIGN),
            ("CORE", self.CORE),
            ("FEATURES", self.FEATURES),
            ("TESTING", self.TESTING),
            ("DEPLOY", self.DEPLOY),
        )


@dataclass(frozen=True)
class PackDefinition:
    pack_id: str
    label_i18n: dict[str, str]
    base_price_eur: int
    estimated_cost_eur: int
    max_complexity_factor: float
    base_modules: tuple[str, ...]
    base_deliverables: tuple[str, ...]
    suggested_addons: tuple[str, ...]
    phases: PhaseWeights
    manual_quote_required: bool

    def label(self, locale: str = "en") -> str:
        return self.label_i18n.get(locale, self.label_i18n["en"])


@dataclass(frozen=True)
class PackCatalog:
    version: str
    packs: dict[str, PackDefinition]

    def get(self, pack_id: str) -> PackDefinition:
        if pack_id not in self.packs:
            raise KeyError(f"unknown pack: {pack_id!r}")
        return self.packs[pack_id]

    def has(self, pack_id: str) -> bool:
        return pack_id in self.packs

    @property
    def pack_ids(self) -> tuple[str, ...]:
        return tuple(self.packs.keys())


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _to_runtime(model: _PacksFileModel) -> PackCatalog:
    packs: dict[str, PackDefinition] = {}
    for pid, p in model.packs.items():
        phases = PhaseWeights(
            ANALYSIS=p.phases.ANALYSIS,
            DESIGN=p.phases.DESIGN,
            CORE=p.phases.CORE,
            FEATURES=p.phases.FEATURES,
            TESTING=p.phases.TESTING,
            DEPLOY=p.phases.DEPLOY,
        )
        packs[pid] = PackDefinition(
            pack_id=pid,
            label_i18n=dict(p.label_i18n),
            base_price_eur=p.base_price_eur,
            estimated_cost_eur=p.estimated_cost_eur,
            max_complexity_factor=p.max_complexity_factor,
            base_modules=tuple(p.base_modules),
            base_deliverables=tuple(p.base_deliverables),
            suggested_addons=tuple(p.suggested_addons),
            phases=phases,
            manual_quote_required=p.manual_quote_required,
        )
    return PackCatalog(version=model.version, packs=packs)


def load_pack_catalog(path: Path | str) -> PackCatalog:
    raw_text = Path(path).read_text(encoding="utf-8")
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PackCatalogError(f"packs JSON invalide: {exc}") from exc
    try:
        model = _PacksFileModel.model_validate(raw)
    except ValidationError as exc:
        raise PackCatalogError(f"packs schema invalide:\n{exc}") from exc
    return _to_runtime(model)


def load_default_pack_catalog() -> PackCatalog:
    return load_pack_catalog(DEFAULT_PACKS_PATH)
