"""V5.1 AUTONOMIE ULTIMATE - Package autonomie (99.9%+).

Sous-modules :
  - autonomy_auditor       : mesure les KPIs d'autonomie (BLOC 13)
  - correlation_id_universal: correlation id bout-en-bout
  - autonomy_chaos_engine  : scenarios de panne nocturne
  - autonomy_ladder        : 5 modes CONTINUE/CONSTRAIN/PROBE/DEFER/ESCALATE
  - autonomy_governor      : gouverneur global
  - autonomy_invariants    : invariants SHA-256 (ex: 'no_escalation_without_proof')
  - ambiguity_resolver     : cascade 4 niveaux avant toute escalation C
  - permission_lease_manager: leases scope+cap+duration avec auto-expiry
  - hard_boundary_registry : scopes qui DOIVENT escalader
  - human_necessity_proof  : preuve structuree obligatoire
  - intervention_learner   : post-mortem chaque intervention
  - calibration_engine     : Brier + isotonic
  - autonomy_simulation_lab: replay historique pour valider nouvelles policies
  - decision_rights_matrix : RACI machine
  - autonomy_cost_model    : cout total (latence + API + humain)
  - autonomy_explainability_api: pourquoi j'ai (ou pas) escalade
"""
