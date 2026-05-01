"""Phase 9D : AI Orchestrator.

Composants :

- providers          : AIProvider Protocol + Stub + Claude/Perplexity/Manus/Internal
- cost_guard         : caps de budget par projet et par appel
- loop_detector      : detection de boucles inefficaces (memo prompt/response)
- retry              : exponential backoff helper
- decisions_logger   : journalise chaque decision dans ai_decisions_log
- router             : choix pondere de provider, fallback chain, integration
                       de tous les composants ci-dessus
- qualification_adapter : RouterBackedClaudeProvider qui adapte AIRouter
                          a `qualification_engine.ClaudeProvider`
"""
from app.saas_factory.ai_orchestrator.cost_guard import (
    BudgetExceededError,
    CostGuard,
    CostLimits,
)
from app.saas_factory.ai_orchestrator.decisions_logger import (
    DecisionRecord,
    DecisionsLogger,
)
from app.saas_factory.ai_orchestrator.loop_detector import (
    LoopDetectedError,
    LoopDetector,
)
from app.saas_factory.ai_orchestrator.providers import (
    PROVIDER_PRICING,
    AIProvider,
    AIProviderError,
    AIResponse,
    ClaudeAIProvider,
    InternalAIProvider,
    ManusAIProvider,
    PerplexityAIProvider,
    StubAIProvider,
)
from app.saas_factory.ai_orchestrator.qualification_adapter import (
    RouterBackedClaudeProvider,
)
from app.saas_factory.ai_orchestrator.retry import (
    RetryExhaustedError,
    TransientAIError,
    with_retry,
)
from app.saas_factory.ai_orchestrator.router import (
    AIRouter,
    RouterDecision,
    RouterFailureError,
    RoutingPolicy,
)

__all__ = [
    "AIProvider",
    "AIProviderError",
    "AIResponse",
    "AIRouter",
    "BudgetExceededError",
    "ClaudeAIProvider",
    "CostGuard",
    "CostLimits",
    "DecisionRecord",
    "DecisionsLogger",
    "InternalAIProvider",
    "LoopDetectedError",
    "LoopDetector",
    "ManusAIProvider",
    "PROVIDER_PRICING",
    "PerplexityAIProvider",
    "RetryExhaustedError",
    "RouterBackedClaudeProvider",
    "RouterDecision",
    "RouterFailureError",
    "RoutingPolicy",
    "StubAIProvider",
    "TransientAIError",
    "with_retry",
]
