"""Phase 9P : Injection liens directs livrables.

Quand un projet atteint un etat livrable (status `delivered` ou similaire),
le `DeliverableLinkInjector` cree automatiquement un `direct_link` (9A)
de type `deliverable_download`, valide 7 jours par defaut, multi-usage
(le client peut re-telecharger plusieurs fois).

Master plan #23 : "Generation 10 livrables tangibles" — ce module est
le hook qui transforme les artefacts internes en URLs cliquables stables.
"""
from app.saas_factory.deliverables.link_injector import (
    DeliverableLinkInjector,
    DeliverableMetadata,
    InjectedDeliverable,
    ProjectNotDeliverableError,
)

__all__ = [
    "DeliverableLinkInjector",
    "DeliverableMetadata",
    "InjectedDeliverable",
    "ProjectNotDeliverableError",
]
