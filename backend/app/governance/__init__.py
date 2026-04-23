"""V5.2 DEHARDCODING - Package governance.

Sous-modules :
  - rules_classifier       : categorise le code en HARDCODED / PARAMETRIZABLE / LEARNABLE / REASONABLE
  - invariants_runtime     : garde-fous durs verifies avant/apres chaque action
  - parameter_manager      : API CRUD pour system_parameters avec bornes dures
  - reasoning_boundaries   : whitelist/blacklist domaines autorises au reasoning
  - reasoning_engine       : oblige le LLM a produire reasoning_trace + confidence
  - drift_detector         : detection derive statistique/performance/qualite
  - reasoning_canary       : shadow -> limited -> full pour nouvelles regles
"""
