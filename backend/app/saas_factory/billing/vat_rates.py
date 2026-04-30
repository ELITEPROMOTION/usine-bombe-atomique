"""Table de TVA par pays (ISO 3166-1 alpha-2).

Couvre 50+ pays : 27 EU + Royaume-Uni + Maghreb + Amerique du Nord +
quelques autres marches strategiques. Source : taux standards 2025
(consultation reglementaire conseillee avant prod).

Note : ce sont les taux **standards** ; les reductions pour services
numeriques B2B intra-EU (TVA inverse) sont gerees par le moteur de
facturation au cas par cas.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class VATRate:
    country: str
    standard_pct: float
    label: str          # ex. "TVA", "VAT", "GST", "MWST"


# 27 EU + UK + Maghreb + USA + Canada + CH + autres = 50+
VAT_TABLE: Final[dict[str, VATRate]] = {
    # --- EU 27 (taux standards 2025) ---
    "AT": VATRate("AT", 20.0, "USt"),    "BE": VATRate("BE", 21.0, "BTW"),
    "BG": VATRate("BG", 20.0, "ДДС"),    "HR": VATRate("HR", 25.0, "PDV"),
    "CY": VATRate("CY", 19.0, "ΦΠΑ"),    "CZ": VATRate("CZ", 21.0, "DPH"),
    "DK": VATRate("DK", 25.0, "MOMS"),   "EE": VATRate("EE", 22.0, "KM"),
    "FI": VATRate("FI", 25.5, "ALV"),    "FR": VATRate("FR", 20.0, "TVA"),
    "DE": VATRate("DE", 19.0, "MwSt"),   "GR": VATRate("GR", 24.0, "ΦΠΑ"),
    "HU": VATRate("HU", 27.0, "ÁFA"),    "IE": VATRate("IE", 23.0, "VAT"),
    "IT": VATRate("IT", 22.0, "IVA"),    "LV": VATRate("LV", 21.0, "PVN"),
    "LT": VATRate("LT", 21.0, "PVM"),    "LU": VATRate("LU", 17.0, "TVA"),
    "MT": VATRate("MT", 18.0, "VAT"),    "NL": VATRate("NL", 21.0, "BTW"),
    "PL": VATRate("PL", 23.0, "VAT"),    "PT": VATRate("PT", 23.0, "IVA"),
    "RO": VATRate("RO", 19.0, "TVA"),    "SK": VATRate("SK", 23.0, "DPH"),
    "SI": VATRate("SI", 22.0, "DDV"),    "ES": VATRate("ES", 21.0, "IVA"),
    "SE": VATRate("SE", 25.0, "Moms"),
    # --- UK + EEA ---
    "GB": VATRate("GB", 20.0, "VAT"),    "NO": VATRate("NO", 25.0, "MVA"),
    "IS": VATRate("IS", 24.0, "VSK"),    "LI": VATRate("LI", 8.1, "MwSt"),
    # --- Maghreb / MENA ---
    "DZ": VATRate("DZ", 19.0, "TVA"),    "MA": VATRate("MA", 20.0, "TVA"),
    "TN": VATRate("TN", 19.0, "TVA"),    "EG": VATRate("EG", 14.0, "VAT"),
    "AE": VATRate("AE", 5.0, "VAT"),     "SA": VATRate("SA", 15.0, "VAT"),
    "TR": VATRate("TR", 20.0, "KDV"),
    # --- Amerique du Nord (TVA fictive : USA pas de federal VAT) ---
    "US": VATRate("US", 0.0, "Sales tax"),  # par etat, gere ailleurs
    "CA": VATRate("CA", 5.0, "GST"),     # federal seulement, +PST/HST par province
    "MX": VATRate("MX", 16.0, "IVA"),
    # --- Asie / Pacifique ---
    "AU": VATRate("AU", 10.0, "GST"),    "NZ": VATRate("NZ", 15.0, "GST"),
    "JP": VATRate("JP", 10.0, "消費税"),  "SG": VATRate("SG", 9.0, "GST"),
    "IN": VATRate("IN", 18.0, "GST"),    "CN": VATRate("CN", 13.0, "增值税"),
    "KR": VATRate("KR", 10.0, "VAT"),
    # --- Autres ---
    "CH": VATRate("CH", 8.1, "MwSt"),    "BR": VATRate("BR", 17.0, "ICMS"),
    "ZA": VATRate("ZA", 15.0, "VAT"),    "AR": VATRate("AR", 21.0, "IVA"),
    "CL": VATRate("CL", 19.0, "IVA"),
}


DEFAULT_VAT_PCT: Final[float] = 20.0


def resolve_vat(country: str) -> VATRate:
    """Retourne le taux pour un code pays. Fallback : entree generique."""
    code = (country or "").upper().strip()
    if code in VAT_TABLE:
        return VAT_TABLE[code]
    # Fallback : on retourne un VATRate avec le taux par defaut
    return VATRate(country=code or "??", standard_pct=DEFAULT_VAT_PCT, label="VAT")
