"""Phase 9I : Legal Framework — conformite GDPR + multi-langues.

5 composants :
- documents       : ToS / Privacy / Cookie Policy x 4 locales (en/fr/ar/es)
- consent_manager : record + query consents (GDPR Art 6.1.a)
- gdpr_export     : Article 20 (right to data portability)
- gdpr_erasure    : Article 17 (right to be forgotten) + retention 17§3

Strategy : on applique GDPR strictement a TOUS les pays (au lieu de
detect-by-country). Plus simple operationnellement, et legal counsel
recommande "highest standard wins" pour eviter les bugs de classification.
Voir ADR-25.

Skip pour V9I : country compliance metadata, PDF generation, auto-detect
law per country.
"""
from app.saas_factory.legal.consent_manager import (
    ConsentAlreadyRecordedError,
    ConsentManager,
    ConsentRecord,
)
from app.saas_factory.legal.documents import (
    LegalDocument,
    LegalDocumentCatalog,
    load_default_legal_catalog,
)
from app.saas_factory.legal.gdpr_erasure import (
    ErasureNotPermittedError,
    ErasureRecord,
    ErasureStatus,
    GDPREraser,
)
from app.saas_factory.legal.gdpr_export import (
    GDPRExporter,
    GDPRExportPackage,
)
from app.saas_factory.legal.types import (
    SUPPORTED_LEGAL_LOCALES,
    DocumentType,
)

__all__ = [
    "ConsentAlreadyRecordedError",
    "ConsentManager",
    "ConsentRecord",
    "DocumentType",
    "ErasureNotPermittedError",
    "ErasureRecord",
    "ErasureStatus",
    "GDPREraser",
    "GDPRExportPackage",
    "GDPRExporter",
    "LegalDocument",
    "LegalDocumentCatalog",
    "SUPPORTED_LEGAL_LOCALES",
    "load_default_legal_catalog",
]
