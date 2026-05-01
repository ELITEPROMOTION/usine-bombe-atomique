"""Mapping entre `projects.status` (V9F) et l'UI client.

Source de verite : la table `projects` (cf. migration 047). Statuts :
  submitted -> qualifying -> assembled -> paywall_pending ->
  in_production -> delivered (-> archived | cancelled)

L'UI client expose un statut + un % d'avancement + une liste de
milestones. On les **derive** ici plutot que d'introduire une nouvelle
table — ADR-33.
"""
from __future__ import annotations

from typing import Final

# Mapping status DB -> status UI (le frontend a son propre vocabulaire)
STATUS_DB_TO_UI: Final[dict[str, str]] = {
    "submitted":      "discovery",
    "qualifying":     "qualified",
    "assembled":      "qualified",
    "paywall_pending": "qualified",
    "in_production":  "in_build",
    "delivered":      "delivered",
    "archived":       "completed",
    "cancelled":      "completed",
}


# Avancement % par status DB (estime, pour l'UI gauge)
PROGRESS_PCT_BY_STATUS: Final[dict[str, int]] = {
    "submitted":      5,
    "qualifying":     15,
    "assembled":      30,
    "paywall_pending": 35,
    "in_production":  65,
    "delivered":      95,
    "archived":       100,
    "cancelled":      100,
}


def derive_ui_status(db_status: str) -> str:
    """Retourne le status UI ou 'discovery' par defaut."""
    return STATUS_DB_TO_UI.get(db_status, "discovery")


def derive_progress_pct(db_status: str) -> int:
    """% d'avancement attendu pour `db_status`."""
    return PROGRESS_PCT_BY_STATUS.get(db_status, 0)
