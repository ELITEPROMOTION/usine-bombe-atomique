"""UBA OSINT — defensive security tooling with hard legal guards.

All modules in this package operate under one of three regimes :

  1. dendani-only  : whitelisted Dendani domains/IPs, no exception
  2. consented     : explicit signed consent stored in DB
  3. public-source : aggregating data from public APIs (no targeting)

Legal compliance : Algeria Loi 18-07 (donnees personnelles) + 09-04 (cybercrime)
+ RGPD (sub-processors). All actions append-only audited via AuditTrail.

DO NOT add a module that bypasses ScopeEnforcer or LegalGuards.
"""
