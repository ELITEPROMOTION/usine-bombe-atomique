"""V5.3 CTC (Continuous Truth Chain) - package.

Modules :
  - source_registry        : registre versionne sources autorisees Tier 1-5
  - evidence_chain         : chaine HMAC-SHA256 append-only
  - meta_truth_auditor     : audite le Truth Engine lui-meme
  - evidence_harvester     : worker continu 24/7
  - assertion_normalizer   : 10 types atomiques
  - truth_graph            : WORM graphe assertions↔entities
  - auto_triangulator      : 7 etapes + verdict TRUE/UNCERTAIN/FALSE/UNKNOWN
  - continuous_validators  : cycles permanent/etendu/profond/complet/chaos
  - seven_layer_validator  : 7 couches sequentielles
  - truth_judge            : extension Judge, verdicts PASS/CP/SF/HF
  - phase_gate_enforcer    : 5 gates nommes
  - assertion_risk_detector: hallucination detection operationnelle
  - rework_engine          : Minor/Major/Critical/Catastrophic
  - truth_chaos_engine     : 10 scenarios pannes controlees
  - truth_budget_manager   : FinOps + circuit breakers
  - truth_explainability_api: transparence totale
  - human_override_manager : overrides traceables
  - truth_engine_snapshotter: dumps 6h + forensics
  - differential_analyzer  : divergences Tier 1 finement analysees
  - backward_compatibility_checker: non-regression
"""
