"""V4.8 - Endpoints Ahmed Inbox.

Boite de reception consolidee : demandes A/B/C + meta + continuous_improvement.
Ahmed ne voit RIEN d'autre : tout le reste est resolu en autonomie.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from app.database import get_pool
from app.inbox import (
    continuous_improvement,
    forms_generator,
    meta_optimizer,
    mit_expert_mode,
)
from app.inbox.user_interaction_router import (
    AccountAsk,
    Case,
    ClarificationAsk,
    InteractionRequest,
    PaymentAsk,
    request_user,
)
from app.orchestration import sensitive_collector

router = APIRouter()


# --- Inbox consolide --------------------------------------------------

@router.get("/inbox")
async def inbox(task_id: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Retourne les pending groupes par type A/B/C."""
    pool = get_pool()
    await sensitive_collector.list_awaiting(pool, task_id=task_id, limit=limit)
    # On recharge depuis DB pour avoir form_type + metadata V4.8
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, task_id, tool_id, form_type, request_kind, fields, context,
                   service_name, why, cost_amount, cost_currency, payment_url,
                   free_alternative, question_id, suggested_answer, criticality,
                   created_at, expires_at
            FROM pending_user_inputs
            WHERE status = 'awaiting' AND expires_at > NOW()
            ORDER BY created_at DESC LIMIT $1
            """, limit,
        )
    buckets: dict[str, list[dict[str, Any]]] = {"A": [], "B": [], "C": [], "legacy": []}
    for r in rows:
        ft = r["form_type"]
        fields = r["fields"]
        if isinstance(fields, str):
            fields = json.loads(fields)
        item = {
            "id": str(r["id"]),
            "task_id": str(r["task_id"]) if r["task_id"] else None,
            "tool_id": r["tool_id"], "form_type": ft,
            "request_kind": r["request_kind"], "fields": fields,
            "context": r["context"],
            "service_name": r["service_name"],
            "why": r["why"], "cost_amount": r["cost_amount"],
            "cost_currency": r["cost_currency"],
            "payment_url": r["payment_url"],
            "free_alternative": r["free_alternative"],
            "question_id": r["question_id"],
            "suggested_answer": r["suggested_answer"],
            "criticality": r["criticality"] or "medium",
            "created_at": r["created_at"].isoformat(),
            "expires_at": r["expires_at"].isoformat(),
        }
        if ft in ("A", "B", "C"):
            buckets[ft].append(item)
        else:
            buckets["legacy"].append(item)
    return {
        "counts": {k: len(v) for k, v in buckets.items()},
        "A_accounts": buckets["A"],
        "B_payments": buckets["B"],
        "C_clarifications": buckets["C"],
        "legacy": buckets["legacy"][:10],
    }


@router.post("/inbox/account")
async def create_account_request(payload: dict) -> dict:
    """Endpoint de test/seed : cree une demande type A via le router."""
    pool = get_pool()
    task_id = payload.get("task_id")
    if not task_id:
        raise HTTPException(400, "task_id required")
    ask = AccountAsk(
        service_name=payload.get("service_name", ""),
        why=payload.get("why", ""),
        org_optional=bool(payload.get("org_optional", False)),
    )
    d = await request_user(pool, InteractionRequest(
        case=Case.ACCOUNT, task_id=task_id,
        actor=payload.get("actor", "manual"),
        payload=ask, context=payload.get("context", ""),
    ))
    return {"allowed": d.allowed, "form_type": d.form_type,
            "pending_request_id": d.pending_request_id, "reason": d.reason}


@router.post("/inbox/payment")
async def create_payment_request(payload: dict) -> dict:
    """Endpoint de test/seed : cree une demande type B via le router."""
    pool = get_pool()
    task_id = payload.get("task_id")
    if not task_id:
        raise HTTPException(400, "task_id required")
    ask = PaymentAsk(
        service_name=payload["service_name"],
        why=payload.get("why", ""),
        cost_amount=payload["cost_amount"],
        cost_currency=payload.get("cost_currency", "USD"),
        duration_months=int(payload.get("duration_months", 1)),
        free_alternative=bool(payload.get("free_alternative", True)),
        payment_url=payload["payment_url"],
    )
    d = await request_user(pool, InteractionRequest(
        case=Case.PAYMENT, task_id=task_id,
        actor=payload.get("actor", "manual"),
        payload=ask, context=payload.get("context", ""),
    ))
    return {"allowed": d.allowed, "form_type": d.form_type,
            "pending_request_id": d.pending_request_id, "reason": d.reason}


@router.post("/inbox/clarification")
async def create_clarification_request(payload: dict) -> dict:
    """Endpoint de test/seed : cree une demande type C via le router."""
    pool = get_pool()
    task_id = payload.get("task_id")
    if not task_id:
        raise HTTPException(400, "task_id required")
    ask = ClarificationAsk(
        question_id=payload["question_id"],
        question=payload["question"],
        why=payload.get("why", ""),
        suggested_answer=payload["suggested_answer"],
        options=list(payload.get("options", [])),
        criticality=payload.get("criticality", "medium"),
    )
    d = await request_user(pool, InteractionRequest(
        case=Case.CLARIFICATION, task_id=task_id,
        actor=payload.get("actor", "manual"),
        payload=ask, context=payload.get("context", ""),
    ))
    return {"allowed": d.allowed, "form_type": d.form_type,
            "pending_request_id": d.pending_request_id, "reason": d.reason}


@router.get("/inbox/blocked")
async def list_blocked(limit: int = 20) -> list[dict]:
    """Journal des demandes utilisateur qui auraient enfreint la doctrine A/B/C."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, task_id, actor, rejected_request, reason, created_at "
            "FROM blocked_user_asks ORDER BY created_at DESC LIMIT $1",
            limit,
        )
    out = []
    for r in rows:
        rr = r["rejected_request"]
        if isinstance(rr, str):
            rr = json.loads(rr)
        out.append({
            "id": r["id"],
            "task_id": str(r["task_id"]) if r["task_id"] else None,
            "actor": r["actor"], "rejected_request": rr,
            "reason": r["reason"],
            "created_at": r["created_at"].isoformat(),
        })
    return out


# --- MIT expert + meta optim + retrospective ------------------------

@router.get("/inbox/mit/playbooks")
async def mit_playbooks() -> dict[str, Any]:
    """Playbook MIT Senior : choix HTTP server / DB / queue avec rationale."""
    return {
        "http_server": mit_expert_mode.pick_http_server().to_dict(),
        "database": mit_expert_mode.pick_db().to_dict(),
        "queue": mit_expert_mode.pick_queue().to_dict(),
    }


@router.post("/inbox/meta/capture")
async def meta_capture() -> dict[str, Any]:
    """Capture un snapshot meta (7j) et declenche self_improver si degradation."""
    pool = get_pool()
    snap = await meta_optimizer.capture_and_analyze(pool)
    return snap.to_dict()


@router.get("/inbox/meta/latest")
async def meta_latest() -> dict[str, Any]:
    """Retourne le dernier snapshot meta-optimiseur."""
    pool = get_pool()
    return await meta_optimizer.latest(pool) or {}


@router.post("/inbox/retro/{task_id}")
async def retro_task(task_id: str) -> dict:
    """Lance une retrospective continuous_improvement sur la tache."""
    pool = get_pool()
    r = await continuous_improvement.run_retrospective(pool, task_id)
    return r.to_dict()


# --- Form rendering preview ----------------------------------------

@router.get("/inbox/preview/account")
async def preview_form_account(service: str = "GitHub", why: str = "Needed for CI") -> dict:
    """Prevue du rendu form type A (pour le frontend)."""
    ask = AccountAsk(service_name=service, why=why)
    return forms_generator.form_account(ask)


@router.get("/inbox/preview/payment")
async def preview_form_payment(
    service: str = "Datadog", cost: str = "15.00", currency: str = "USD",
    url: str = "https://datadoghq.com/billing",
) -> dict:
    """Prevue du rendu form type B."""
    ask = PaymentAsk(service_name=service, why="Observability production",
                      cost_amount=cost, cost_currency=currency,
                      duration_months=1, free_alternative=True,
                      payment_url=url)
    return forms_generator.form_payment(ask)


@router.get("/inbox/preview/clarification")
async def preview_form_clarification() -> dict:
    """Prevue du rendu form type C."""
    ask = ClarificationAsk(
        question_id="Q-001",
        question="Quelle frequence de backup voulez-vous ?",
        why="Impacte cout + RPO",
        suggested_answer="Quotidienne a 02:00 UTC",
        options=["Horaire", "Quotidienne", "Hebdomadaire"],
        criticality="high",
    )
    return forms_generator.form_clarification(ask)
