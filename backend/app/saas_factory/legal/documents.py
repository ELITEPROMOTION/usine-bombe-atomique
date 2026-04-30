"""LegalDocumentCatalog : ToS / Privacy / Cookie Policy x 4 locales.

⚠ Le contenu ci-dessous est un **placeholder** structurel. Avant prod,
faire reviser le texte par un legal counsel local pour chaque locale.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Final

from app.saas_factory.legal.types import (
    SUPPORTED_LEGAL_LOCALES,
    DocumentType,
)

CURRENT_VERSION: Final[str] = "2026-04-30"


@dataclass(frozen=True)
class LegalDocument:
    document_type: DocumentType
    locale: str
    version: str
    title: str
    body_md: str            # markdown brut, render HTML cote UI
    checksum_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.checksum_sha256:
            sha = hashlib.sha256(
                self.body_md.encode("utf-8"),
            ).hexdigest()
            object.__setattr__(self, "checksum_sha256", sha)


# ---------------------------------------------------------------------------
# Templates minimalistes : structure complete, contenu placeholder
# ---------------------------------------------------------------------------
_TOS_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "title": "Terms of Service — UBA Studio Platform",
        "body": (
            "# Terms of Service\n\n"
            "**Effective date:** 2026-04-30\n\n"
            "## 1. Acceptance\n"
            "By using UBA Studio Platform, you accept these terms.\n\n"
            "## 2. Service description\n"
            "UBA Studio delivers SaaS projects through automated orchestration.\n\n"
            "## 3. Payment\n"
            "Project pricing is fixed at qualification time. Payment is "
            "due before production starts.\n\n"
            "## 4. Refund policy\n"
            "Full refund if SLA is violated. Partial refund proportional "
            "to delivered phases otherwise.\n\n"
            "## 5. Intellectual property\n"
            "Delivered code belongs to the client. UBA retains rights on "
            "internal orchestration framework.\n\n"
            "## 6. Liability\n"
            "Liability capped at the project price.\n\n"
            "## 7. Governing law\n"
            "French law applies. Disputes resolved in Paris commercial court.\n\n"
            "## 8. Contact\n"
            "support@uba.studio\n\n"
            "[PLACEHOLDER — review with legal counsel before production]"
        ),
    },
    "fr": {
        "title": "Conditions Generales d'Utilisation — UBA Studio Platform",
        "body": (
            "# Conditions Generales d'Utilisation\n\n"
            "**Date d'effet :** 2026-04-30\n\n"
            "## 1. Acceptation\n"
            "En utilisant UBA Studio Platform, vous acceptez ces conditions.\n\n"
            "## 2. Description du service\n"
            "UBA Studio livre des projets SaaS via orchestration automatique.\n\n"
            "## 3. Paiement\n"
            "Le prix est fige a la qualification. Le paiement est exige "
            "avant le demarrage de la production.\n\n"
            "## 4. Politique de remboursement\n"
            "Remboursement integral si SLA viole. Sinon remboursement "
            "proportionnel aux phases livrees.\n\n"
            "## 5. Propriete intellectuelle\n"
            "Le code livre appartient au client. UBA conserve les droits "
            "sur le framework d'orchestration interne.\n\n"
            "## 6. Responsabilite\n"
            "Responsabilite plafonnee au prix du projet.\n\n"
            "## 7. Droit applicable\n"
            "Droit francais. Tribunal de commerce de Paris competent.\n\n"
            "## 8. Contact\n"
            "support@uba.studio\n\n"
            "[PLACEHOLDER — a reviser avec un avocat avant production]"
        ),
    },
    "ar": {
        "title": "شروط الخدمة — UBA Studio Platform",
        "body": (
            "# شروط الخدمة\n\n"
            "**تاريخ السريان :** 2026-04-30\n\n"
            "## 1. القبول\n"
            "باستخدام UBA Studio Platform، فإنك توافق على هذه الشروط.\n\n"
            "## 2. وصف الخدمة\n"
            "تقدم UBA Studio مشاريع SaaS عبر التنسيق الآلي.\n\n"
            "[PLACEHOLDER — للمراجعة مع مستشار قانوني]"
        ),
    },
    "es": {
        "title": "Terminos de Servicio — UBA Studio Platform",
        "body": (
            "# Terminos de Servicio\n\n"
            "**Fecha de entrada en vigor:** 2026-04-30\n\n"
            "## 1. Aceptacion\n"
            "Al usar UBA Studio Platform, usted acepta estos terminos.\n\n"
            "## 2. Descripcion del servicio\n"
            "UBA Studio entrega proyectos SaaS mediante orquestacion automatica.\n\n"
            "[PLACEHOLDER — revisar con asesor legal antes de produccion]"
        ),
    },
}

_PRIVACY_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "title": "Privacy Policy — UBA Studio Platform",
        "body": (
            "# Privacy Policy (GDPR-compliant)\n\n"
            "**Effective date:** 2026-04-30\n\n"
            "## Data we collect\n"
            "- Identity: email, full name, company name, country, locale\n"
            "- Project: brief description, pack selection, branding choices\n"
            "- Payment: amount, currency, status (no card data — Stripe handles)\n"
            "- Technical: IP (hashed), audit log entries\n\n"
            "## Legal basis (Art. 6 GDPR)\n"
            "- Contract performance (Art. 6.1.b) for project delivery\n"
            "- Legal obligation (Art. 6.1.c) for invoices, audit trails\n"
            "- Consent (Art. 6.1.a) for marketing emails (opt-in)\n\n"
            "## Your rights\n"
            "- **Right to access** (Art. 15): export all your data via "
            "`/admin/gdpr/export/{project_id}`\n"
            "- **Right to erasure** (Art. 17): request via support@uba.studio\n"
            "  ⚠ Audit trail (mandates, evidence_ledger) is retained per "
            "Art. 17§3 (legal obligation).\n"
            "- **Right to portability** (Art. 20): JSON export above\n"
            "- **Right to lodge a complaint**: contact your DPA (CNIL in France)\n\n"
            "## Retention\n"
            "- Active project data: until project archived\n"
            "- Invoices: 10 years (legal obligation)\n"
            "- Audit trail: 7 years (compliance)\n\n"
            "## Cross-border transfers\n"
            "Data hosted in EU. Stripe (US) under SCC. Anthropic (US) under SCC.\n\n"
            "## Contact\n"
            "DPO: dpo@uba.studio\n\n"
            "[PLACEHOLDER — review with DPO and legal counsel]"
        ),
    },
    "fr": {
        "title": "Politique de Confidentialite — UBA Studio Platform",
        "body": (
            "# Politique de Confidentialite (conforme RGPD)\n\n"
            "**Date d'effet :** 2026-04-30\n\n"
            "## Donnees collectees\n"
            "- Identite : email, nom complet, raison sociale, pays, langue\n"
            "- Projet : description brief, pack choisi, branding\n"
            "- Paiement : montant, devise, statut (pas de donnee carte — Stripe)\n"
            "- Technique : IP (hashee), entrees audit log\n\n"
            "## Base legale (Art. 6 RGPD)\n"
            "- Execution du contrat (Art. 6.1.b) pour la livraison\n"
            "- Obligation legale (Art. 6.1.c) pour factures, audit trails\n"
            "- Consentement (Art. 6.1.a) pour emails marketing (opt-in)\n\n"
            "## Vos droits\n"
            "- **Droit d'acces** (Art. 15) : export via "
            "`/admin/gdpr/export/{project_id}`\n"
            "- **Droit a l'effacement** (Art. 17) : demande via "
            "support@uba.studio\n"
            "  ⚠ Audit trail (mandats, evidence_ledger) conserve selon "
            "Art. 17§3 (obligation legale).\n"
            "- **Droit a la portabilite** (Art. 20) : export JSON ci-dessus\n"
            "- **Droit de reclamation** : contacter la CNIL en France\n\n"
            "## Conservation\n"
            "- Donnees projet actives : jusqu'a l'archivage\n"
            "- Factures : 10 ans (obligation legale)\n"
            "- Audit trail : 7 ans\n\n"
            "## Transferts hors UE\n"
            "Donnees hebergees UE. Stripe (US) sous CCT. Anthropic (US) sous CCT.\n\n"
            "## Contact\n"
            "DPO : dpo@uba.studio\n\n"
            "[PLACEHOLDER — a reviser avec DPO et legal counsel]"
        ),
    },
    "ar": {
        "title": "سياسة الخصوصية — UBA Studio Platform",
        "body": (
            "# سياسة الخصوصية (متوافقة مع GDPR)\n\n"
            "**تاريخ السريان :** 2026-04-30\n\n"
            "[PLACEHOLDER — مراجعة قانونية مطلوبة]"
        ),
    },
    "es": {
        "title": "Politica de Privacidad — UBA Studio Platform",
        "body": (
            "# Politica de Privacidad (conforme RGPD)\n\n"
            "**Fecha de entrada en vigor:** 2026-04-30\n\n"
            "[PLACEHOLDER — revision legal requerida]"
        ),
    },
}

_COOKIE_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "title": "Cookie Policy — UBA Studio Platform",
        "body": (
            "# Cookie Policy\n\n"
            "## Functional cookies (essential, no opt-out)\n"
            "- Session token, CSRF, auth\n\n"
            "## Analytics cookies (opt-in)\n"
            "- PostHog (product analytics)\n\n"
            "## Marketing cookies (opt-in)\n"
            "- None for now\n\n"
            "[PLACEHOLDER]"
        ),
    },
    "fr": {
        "title": "Politique Cookies — UBA Studio Platform",
        "body": (
            "# Politique Cookies\n\n"
            "## Cookies fonctionnels (essentiels, non desactivables)\n"
            "- Token session, CSRF, auth\n\n"
            "## Cookies analytics (opt-in)\n"
            "- PostHog\n\n"
            "## Cookies marketing (opt-in)\n"
            "- Aucun pour l'instant\n\n"
            "[PLACEHOLDER]"
        ),
    },
    "ar": {
        "title": "سياسة ملفات تعريف الارتباط — UBA Studio Platform",
        "body": "# سياسة ملفات تعريف الارتباط\n\n[PLACEHOLDER]",
    },
    "es": {
        "title": "Politica de Cookies — UBA Studio Platform",
        "body": "# Politica de Cookies\n\n[PLACEHOLDER]",
    },
}


_TEMPLATES_BY_TYPE: dict[DocumentType, dict[str, dict[str, str]]] = {
    DocumentType.TOS: _TOS_TEMPLATES,
    DocumentType.PRIVACY: _PRIVACY_TEMPLATES,
    DocumentType.COOKIE_POLICY: _COOKIE_TEMPLATES,
}


@dataclass(frozen=True)
class LegalDocumentCatalog:
    version: str
    documents: dict[tuple[DocumentType, str], LegalDocument] = field(
        default_factory=dict,
    )

    def get(self, doc_type: DocumentType, locale: str) -> LegalDocument:
        if locale not in SUPPORTED_LEGAL_LOCALES:
            locale = "en"
        key = (doc_type, locale)
        if key not in self.documents:
            raise KeyError(f"document {doc_type.value}/{locale} introuvable")
        return self.documents[key]

    def has(self, doc_type: DocumentType, locale: str) -> bool:
        return (doc_type, locale) in self.documents


def load_default_legal_catalog() -> LegalDocumentCatalog:
    docs: dict[tuple[DocumentType, str], LegalDocument] = {}
    for doc_type, lang_map in _TEMPLATES_BY_TYPE.items():
        for locale, content in lang_map.items():
            docs[(doc_type, locale)] = LegalDocument(
                document_type=doc_type,
                locale=locale,
                version=CURRENT_VERSION,
                title=content["title"],
                body_md=content["body"],
            )
    return LegalDocumentCatalog(
        version=CURRENT_VERSION,
        documents=docs,
    )
