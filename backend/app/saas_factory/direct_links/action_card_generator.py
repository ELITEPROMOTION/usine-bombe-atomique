"""Generateur de cartes d'action a partir d'un IssuedLink.

Une `ActionCard` est la representation visuelle/textuelle d'un direct-link :
elle est utilisee par les renderers email, dashboard, push, SMS. C'est une
structure pure, sans HTML — chaque renderer decide de sa presentation.

Les chaines i18n sont prises dans le `Catalog` (locales en/fr). Les
placeholders `{service}`, `{project_name}`, `{domain}` sont substitues
depuis le `metadata` passe a `render()`.

Si une variable de substitution est manquante dans metadata, on conserve
le placeholder litteral plutot que de planter — la card est cosmetique,
pas critique.
"""
from __future__ import annotations

import logging
import string
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.saas_factory.direct_links.catalog import DEFAULT_LOCALE, Catalog
from app.saas_factory.direct_links.direct_link_generator import IssuedLink

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionCard:
    title: str
    description: str
    cta_label: str
    cta_url: str
    icon: str
    locale: str
    expires_at: datetime
    action_type: str
    metadata: dict[str, Any]


class _SafeFormatter(string.Formatter):
    """Formatter tolerant : laisse `{x}` litteral si `x` n'est pas fourni."""

    def get_value(self, key: int | str, args: tuple, kwargs: dict[str, Any]) -> Any:
        if isinstance(key, str):
            if key in kwargs:
                return kwargs[key]
            return "{" + key + "}"
        return super().get_value(key, args, kwargs)


_FORMATTER = _SafeFormatter()


def _safe_format(template: str, ctx: dict[str, Any]) -> str:
    try:
        return _FORMATTER.format(template, **ctx)
    except (IndexError, ValueError) as exc:
        logger.debug("safe_format fallback (%s): %s", exc, template[:80])
        return template


class ActionCardGenerator:
    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    def render(
        self,
        link: IssuedLink,
        *,
        locale: str = DEFAULT_LOCALE,
        context: dict[str, Any] | None = None,
    ) -> ActionCard:
        entry = self._catalog.get(link.action_type)
        chosen_locale = locale if locale in entry.locales else DEFAULT_LOCALE
        strings = entry.localize(chosen_locale)
        ctx = dict(context or {})

        return ActionCard(
            title=_safe_format(strings.title, ctx),
            description=_safe_format(strings.description, ctx),
            cta_label=_safe_format(strings.cta_label, ctx),
            cta_url=link.url,
            icon=entry.icon,
            locale=chosen_locale,
            expires_at=link.expires_at,
            action_type=link.action_type,
            metadata=ctx,
        )
