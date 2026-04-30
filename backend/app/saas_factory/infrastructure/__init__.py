"""Phase 9G : Hostinger Provisioning.

5 composants :
- HostingerClient   : wrapper httpx authentifie (Bearer HOSTINGER_API_TOKEN)
- DomainManager     : search libre, purchase GATED par payment_id
- VPSProvisioner    : list_plans libre, create_instance GATED par payment_id
- SSLManager        : Let's Encrypt request / renew / list
- BackupManager     : schedule daily / list / restore

Tous les chemins reseau reels (`_do_request`) sont marques
`# pragma: no cover` — aucun appel reel emis dans les tests. La bascule
en mode live necessite (a) UBA_LIVE_HOSTINGER=1 et (b) un payment_id
valide sur les operations facturables. Voir ADR-18.
"""
from app.saas_factory.infrastructure.backup_manager import (
    BackupInfo,
    BackupManager,
)
from app.saas_factory.infrastructure.domain_manager import (
    DomainManager,
    DomainPurchaseRequest,
)
from app.saas_factory.infrastructure.hostinger_client import (
    HostingerAPIError,
    HostingerClient,
    HostingerLiveDisabledError,
    PaymentIdRequiredError,
    StubHostingerClient,
)
from app.saas_factory.infrastructure.ssl_manager import (
    SSLCertificate,
    SSLManager,
)
from app.saas_factory.infrastructure.types import (
    DomainSearchResult,
    HostingerResource,
    HostingerResourceStatus,
    HostingerResourceType,
    VPSCreateRequest,
    VPSInstance,
    VPSPlan,
)
from app.saas_factory.infrastructure.vps_provisioner import VPSProvisioner

__all__ = [
    "BackupInfo",
    "BackupManager",
    "DomainManager",
    "DomainPurchaseRequest",
    "DomainSearchResult",
    "HostingerAPIError",
    "HostingerClient",
    "HostingerLiveDisabledError",
    "HostingerResource",
    "HostingerResourceStatus",
    "HostingerResourceType",
    "PaymentIdRequiredError",
    "SSLCertificate",
    "SSLManager",
    "StubHostingerClient",
    "VPSCreateRequest",
    "VPSInstance",
    "VPSPlan",
    "VPSProvisioner",
]
