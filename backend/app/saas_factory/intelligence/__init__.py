"""Phase 9C : Intelligence Engine.

4 moteurs orchestres + 9 packs contextuels :

- packs                : 9 packs (E-Commerce S/M/L, SaaS S/M/L, Mobile, API B2B, Custom)
- pricing_engine       : 15 coefficients x facettes projet, marge >= 50%
- qualification_engine : analyse CDC via ClaudeProvider (Protocol injectable)
- assembly_engine      : compose qualification + pricing + pack -> AssembledProject
- progression_engine   : poids des phases, calcul %, declenchement paywall 20%

Le QualificationEngine n'emet AUCUN appel reel a Claude en Phase 9C : on utilise
un Protocol injectable. Le branchement reel se fait en Phase 9D via l'AI Router.
"""
from app.saas_factory.intelligence.assembly_engine import (
    AssembledProject,
    AssemblyEngine,
    AssemblyOutcome,
)
from app.saas_factory.intelligence.packs.catalog import (
    PackCatalog,
    PackDefinition,
    PackId,
    PhaseWeights,
    load_default_pack_catalog,
)
from app.saas_factory.intelligence.pricing_engine import (
    PricingBreakdown,
    PricingEngine,
    PricingResult,
    ProjectFacets,
)
from app.saas_factory.intelligence.progression_engine import (
    PROGRESSION_PHASES,
    ProgressionEngine,
    ProgressionSnapshot,
    ProjectPhase,
)
from app.saas_factory.intelligence.qualification_engine import (
    ClaudeProvider,
    Qualification,
    QualificationEngine,
    StubClaudeProvider,
)

__all__ = [
    "AssembledProject",
    "AssemblyEngine",
    "AssemblyOutcome",
    "ClaudeProvider",
    "PROGRESSION_PHASES",
    "PackCatalog",
    "PackDefinition",
    "PackId",
    "PhaseWeights",
    "PricingBreakdown",
    "PricingEngine",
    "PricingResult",
    "ProgressionEngine",
    "ProgressionSnapshot",
    "ProjectFacets",
    "ProjectPhase",
    "Qualification",
    "QualificationEngine",
    "StubClaudeProvider",
    "load_default_pack_catalog",
]
