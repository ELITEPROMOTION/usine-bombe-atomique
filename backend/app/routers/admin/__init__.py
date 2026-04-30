"""Phase 9N : Dashboard Admin Ahmed.

Routers /admin/* qui exposent (avec auth admin token) :

- ai            : FinOps + AI router policy + decisions log
- handoffs      : list/cancel/escalate
- projects      : list + status override
- direct_links  : list + revoke
- setup_wizard  : full CRUD pour le wizard 9B
- onboarding    : funnel + sessions list

Auth : header `X-Admin-Token` matche `UBA_ADMIN_TOKEN` env (stopgap, ADR-17).
Toutes les actions de mutation passent par AdminAuditLogger -> table
admin_actions (migration 048).
"""
from app.routers.admin.dependencies import (
    AdminAuditLogger,
    AdminPrincipal,
    get_admin_audit_logger,
    get_current_admin,
)

__all__ = [
    "AdminAuditLogger",
    "AdminPrincipal",
    "get_admin_audit_logger",
    "get_current_admin",
]
