"""Upgrade 5 - Tool Provisioner : orchestrate l'ouverture d'un compte SaaS.

Flow :
 1. Detecter qu'un outil est necessaire (domain + spec + recommendation)
 2. Demander confirmation a l'utilisateur (sensitive_collector)
 3. Appeler BrowserOpsAgent sur le flow pre-enregistre
 4. A chaque FieldRequest generee, persister dans pending_user_inputs
 5. Attendre la soumission
 6. Continuer, jusqu'a obtention de la cle API
 7. Stocker la cle dans Vault
 8. Enregistrer dans tool_registry
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import asyncpg

from app.integrations.vault_client import get_vault
from app.orchestration import audit_events, evidence_ledger, sensitive_collector, tool_registry
from app.provisioning.browser_ops_agent import (
    BrowserOpsAgent,
    get_flow,
)

logger = logging.getLogger(__name__)


@dataclass
class ProvisionOutcome:
    tool_id: str
    status: str            # success | awaiting_user | failed | unknown_tool
    pending_request_id: str | None = None
    vault_path: str | None = None
    message: str = ""


async def provision(
    pool: asyncpg.Pool, task_id: str, tool_id: str,
    provided_values: dict[str, str] | None = None,
    dry_run: bool = True,
) -> ProvisionOutcome:
    """Lance (ou continue) le provisioning d'un outil pour une tache."""
    flow = get_flow(tool_id)
    if not flow:
        return ProvisionOutcome(tool_id=tool_id, status="unknown_tool",
                                 message=f"Aucun flow pre-enregistre pour {tool_id}")

    # Journaliser l'intention dans evidence_ledger
    await evidence_ledger.record(
        pool, kind="decision", actor="tool_provisioner",
        payload={"tool_id": tool_id, "dry_run": dry_run,
                 "required_inputs": flow.required_user_inputs},
        task_id=task_id,
    )

    agent = BrowserOpsAgent(dry_run=dry_run)
    outcome = await agent.execute(flow, provided_values=provided_values)

    if not outcome.success and outcome.next_request is not None:
        req_id = await sensitive_collector.persist_request(
            pool, task_id=task_id, req=outcome.next_request, tool_id=tool_id,
        )
        await tool_registry.register(pool, tool_registry.Tool(
            tool_id=tool_id, name=flow.tool_name,
            tool_type="saas", url=flow.signup_url,
            status="needs_user_input",
        ))
        await audit_events.emit(
            pool, action="tool_awaiting_input",
            actor="tool_provisioner",
            payload={"tool_id": tool_id, "request_id": req_id,
                     "message": outcome.message},
            task_id=task_id,
        )
        return ProvisionOutcome(
            tool_id=tool_id, status="awaiting_user",
            pending_request_id=req_id,
            message=outcome.message,
        )

    if outcome.success:
        # Recuperation simulee de la cle (en live, elle viendrait de la page
        # apres login). On lit `provided_values["api_key"]` si dispo.
        api_key = (provided_values or {}).get("api_key", "")
        vault = get_vault()
        vault_path = f"tools/{tool_id}"
        if api_key and vault.is_available():
            vault.put(vault_path, {"api_key": api_key})
        await tool_registry.register(pool, tool_registry.Tool(
            tool_id=tool_id, name=flow.tool_name, tool_type="saas",
            url=flow.signup_url, api_key_vault_path=vault_path,
            status="connected" if api_key else "pending_setup",
        ))
        await audit_events.emit(
            pool, action="tool_provisioned", actor="tool_provisioner",
            payload={"tool_id": tool_id, "vault_path": vault_path,
                     "has_api_key": bool(api_key)},
            task_id=task_id,
        )
        return ProvisionOutcome(
            tool_id=tool_id, status="success",
            vault_path=vault_path,
            message="Outil provisionne",
        )

    return ProvisionOutcome(
        tool_id=tool_id, status="failed",
        message=outcome.message,
    )
