"""V5.4 PARTIE 2.4 - Schemas centralises Pydantic v2.

9 types de traces + reports (uncertainty, bias, constitutional, meta).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ProblemType = Literal["simple", "moderate", "complex", "creative",
                       "sequential", "ambiguous"]
TraceStatus = Literal["in_progress", "completed", "failed", "killed", "cached"]


class ReasoningStep(BaseModel):
    index: int
    content: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1, default=0.5)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChainTrace(BaseModel):
    """Chain of Thought trace."""
    mode: Literal["zero_shot", "few_shot", "program_aided",
                   "self_consistent", "structured"]
    steps: list[ReasoningStep]
    intermediate_conclusions: list[str] = Field(default_factory=list)
    alternatives_rejected: list[dict[str, str]] = Field(default_factory=list)
    final_answer: str
    confidence: float = Field(ge=0, le=1, default=0)
    verification_trace: dict[str, Any] = Field(default_factory=dict)


class TreeNode(BaseModel):
    node_id: str
    parent_id: str | None = None
    depth: int = 0
    thought: str
    value: float = Field(ge=0, le=1, default=0)
    pruned: bool = False


class TreeTrace(BaseModel):
    strategy: Literal["dfs", "bfs", "best_first", "mcts"]
    max_depth: int
    branching_factor: int
    nodes: list[TreeNode] = Field(default_factory=list)
    best_path: list[str] = Field(default_factory=list)
    final_score: float = Field(ge=0, le=1, default=0)


class GraphTrace(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)
    convergences: list[dict[str, Any]] = Field(default_factory=list)
    dominant_paths: list[list[str]] = Field(default_factory=list)


class DebateRound(BaseModel):
    round_index: int
    role: str
    argument: str
    counter: str | None = None


class DebateTrace(BaseModel):
    role_a: str
    role_b: str
    rounds: list[DebateRound] = Field(default_factory=list)
    devils_advocate_activated: bool = False
    judge_verdict: Literal["A_wins", "B_wins", "hybrid_synthesis", "escalate"]
    judge_rationale: str


class ReflectionCycle(BaseModel):
    cycle: int
    v1_solution: str
    v2_solution: str
    premortem_findings: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    improvement_delta: float = 0.0
    converged: bool = False


class ReflectionTrace(BaseModel):
    cycles: list[ReflectionCycle] = Field(default_factory=list)
    final_solution: str
    max_cycles: int = 3


class ConstitutionalReport(BaseModel):
    principle_results: dict[str, bool]        # {"P1": True, "P2": False, ...}
    violations: list[dict[str, str]] = Field(default_factory=list)
    regeneration_constraints: list[str] = Field(default_factory=list)
    final_pass: bool = False


class UncertaintyReport(BaseModel):
    aleatory: float = Field(ge=0, le=1, default=0)
    epistemic: float = Field(ge=0, le=1, default=0)
    ontological: float = Field(ge=0, le=1, default=0)
    computational: float = Field(ge=0, le=1, default=0)
    credible_low: float = Field(ge=0, le=1, default=0)
    credible_high: float = Field(ge=0, le=1, default=1)
    sensitivities: list[dict[str, Any]] = Field(default_factory=list)


class BiasReport(BaseModel):
    biases_detected: list[str] = Field(default_factory=list)
    mitigations_applied: list[dict[str, str]] = Field(default_factory=list)


class MetaCognitiveReport(BaseModel):
    problem_class: ProblemType
    strategy_selected: str
    resources_allocated: dict[str, Any] = Field(default_factory=dict)
    stuck_states_detected: int = 0
    loops_detected: int = 0
    stop_reason: str | None = None


class DecisionRecord(BaseModel):
    decision_id: str | None = None
    chosen: Any
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    justification: str = ""
    confidence: float = Field(ge=0, le=1, default=0)
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"


class ReasoningTrace(BaseModel):
    """Trace master reliant toutes les sous-traces."""
    trace_id: str | None = None
    task_id: str | None = None
    problem_statement: str
    problem_type: ProblemType
    technique_path: list[str] = Field(default_factory=list)
    chain: ChainTrace | None = None
    tree: TreeTrace | None = None
    graph: GraphTrace | None = None
    debate: DebateTrace | None = None
    reflection: ReflectionTrace | None = None
    constitutional: ConstitutionalReport | None = None
    uncertainty: UncertaintyReport | None = None
    bias: BiasReport | None = None
    meta: MetaCognitiveReport | None = None
    final_answer: str | None = None
    final_confidence: float = Field(ge=0, le=1, default=0)
    reasoning_fingerprint: str = ""
    total_tokens: int = 0
    total_duration_ms: int = 0
    status: TraceStatus = "in_progress"
