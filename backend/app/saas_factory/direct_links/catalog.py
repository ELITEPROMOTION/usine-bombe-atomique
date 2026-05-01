"""Chargement et validation du catalogue d'actions direct-link.

Le catalogue (`catalog.json`) liste les types d'actions supportes par le
framework. Chaque type contient un TTL par defaut, un mode single-use,
un flag requires_mandate, le callback_path et les chaines i18n EN/FR.

Le catalogue est valide a l'import via Pydantic v2 ; toute action mal
formee leve une `CatalogValidationError`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import BaseModel, Field, ValidationError, field_validator

DEFAULT_CATALOG_PATH: Final[Path] = Path(__file__).parent / "catalog.json"
SUPPORTED_LOCALES: Final[frozenset[str]] = frozenset({"en", "fr"})
DEFAULT_LOCALE: Final[str] = "en"
MAX_TTL_SECONDS: Final[int] = 30 * 24 * 3600  # 30 jours


class CatalogValidationError(ValueError):
    pass


class _LocaleStringsModel(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    cta_label: str = Field(min_length=1, max_length=50)


class _CatalogEntryModel(BaseModel):
    default_ttl_seconds: int = Field(ge=60, le=MAX_TTL_SECONDS)
    single_use: bool
    requires_mandate: bool
    callback_path: str = Field(pattern=r"^/[a-zA-Z0-9_\-/]+$")
    icon: str = Field(min_length=1, max_length=50)
    locales: dict[str, _LocaleStringsModel]

    @field_validator("locales")
    @classmethod
    def _check_locales(cls, v: dict[str, _LocaleStringsModel]) -> dict[str, _LocaleStringsModel]:
        if DEFAULT_LOCALE not in v:
            raise ValueError(f"locale '{DEFAULT_LOCALE}' (fallback) is required")
        unknown = set(v) - SUPPORTED_LOCALES
        if unknown:
            raise ValueError(f"unsupported locales: {sorted(unknown)}")
        return v


class _CatalogModel(BaseModel):
    version: str
    actions: dict[str, _CatalogEntryModel]


# Versions runtime (frozen dataclasses) — plus ergonomiques en lecture.
@dataclass(frozen=True)
class LocaleStrings:
    title: str
    description: str
    cta_label: str


@dataclass(frozen=True)
class CatalogEntry:
    action_type: str
    default_ttl_seconds: int
    single_use: bool
    requires_mandate: bool
    callback_path: str
    icon: str
    locales: dict[str, LocaleStrings]

    def localize(self, locale: str) -> LocaleStrings:
        if locale in self.locales:
            return self.locales[locale]
        return self.locales[DEFAULT_LOCALE]


@dataclass(frozen=True)
class Catalog:
    version: str
    entries: dict[str, CatalogEntry]

    def get(self, action_type: str) -> CatalogEntry:
        if action_type not in self.entries:
            raise KeyError(f"unknown action_type: {action_type!r}")
        return self.entries[action_type]

    def has(self, action_type: str) -> bool:
        return action_type in self.entries

    @property
    def action_types(self) -> tuple[str, ...]:
        return tuple(self.entries.keys())


def _to_runtime(model: _CatalogModel) -> Catalog:
    entries: dict[str, CatalogEntry] = {}
    for at, e in model.actions.items():
        loc = {
            k: LocaleStrings(title=ls.title, description=ls.description, cta_label=ls.cta_label)
            for k, ls in e.locales.items()
        }
        entries[at] = CatalogEntry(
            action_type=at,
            default_ttl_seconds=e.default_ttl_seconds,
            single_use=e.single_use,
            requires_mandate=e.requires_mandate,
            callback_path=e.callback_path,
            icon=e.icon,
            locales=loc,
        )
    return Catalog(version=model.version, entries=entries)


def load_catalog(path: Path | str) -> Catalog:
    """Charge un catalogue JSON depuis un chemin arbitraire (utile pour les tests)."""
    raw_text = Path(path).read_text(encoding="utf-8")
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise CatalogValidationError(f"catalog JSON invalide: {exc}") from exc
    try:
        model = _CatalogModel.model_validate(raw)
    except ValidationError as exc:
        raise CatalogValidationError(f"catalog schema invalide:\n{exc}") from exc
    return _to_runtime(model)


def load_default_catalog() -> Catalog:
    """Charge `catalog.json` colocalise dans le package."""
    return load_catalog(DEFAULT_CATALOG_PATH)
