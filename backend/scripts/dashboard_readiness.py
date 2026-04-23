#!/usr/bin/env python3
"""V4.8 - Dashboard readiness generator.

Ecrit `dashboard_readiness.md` a la racine du repo avec :
- Outils reellement connectes (healthcheck live)
- Formulaires A/B/C en attente
- Niveau d'autonomie (% des actions faisables sans Ahmed)
- Prochaine auto-amelioration programmee

Usage :
    python backend/scripts/dashboard_readiness.py
    # ou avec override :
    UBA_BACKEND_URL=http://backend:8000 python .../dashboard_readiness.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


BACKEND = os.environ.get("UBA_BACKEND_URL", "http://localhost:8000")
REPO = Path(__file__).resolve().parent.parent.parent


def fetch(path: str) -> dict | list | None:
    try:
        with urllib.request.urlopen(f"{BACKEND}{path}", timeout=15) as r:
            return json.loads(r.read())
    except Exception as exc:
        print(f"  ! {path} -> {exc}", file=sys.stderr)
        return None


def _section_tools() -> list[str]:
    tools = fetch("/api/v1/tools") or []
    integ = fetch("/api/v1/integrations/status") or {}
    lines = ["## Outils reellement connectes", ""]
    lines.append(f"- **Vault** : {'UP' if integ.get('vault', {}).get('available') else 'DOWN'}")
    sonar = integ.get("sonarqube", {})
    lines.append(
        f"- **SonarQube** : {sonar.get('status', 'unknown')}"
        f" (version {sonar.get('version', '?')})"
    )
    lines.append(f"- **Tools registres** : {len(tools) if isinstance(tools, list) else 0}")
    if isinstance(tools, list):
        for t in tools[:20]:
            lines.append(
                f"  - `{t.get('tool_id','?')}` ({t.get('tool_type','?')}) : "
                f"{t.get('status','?')} · capabilities={len(t.get('capabilities') or [])}"
            )
    return lines


def _section_inbox() -> list[str]:
    data = fetch("/api/v1/inbox") or {}
    counts = data.get("counts", {})
    lines = [
        "", "## Formulaires A/B/C en attente", "",
        f"- Type A (comptes) : **{counts.get('A', 0)}**",
        f"- Type B (paiements) : **{counts.get('B', 0)}**",
        f"- Type C (clarifications) : **{counts.get('C', 0)}**",
        f"- Legacy (V4.3 pre-doctrine) : {counts.get('legacy', 0)}",
    ]
    for b in ("A_accounts", "B_payments", "C_clarifications"):
        bucket = data.get(b) or []
        if not bucket:
            continue
        lines.append(f"\n### {b}")
        for it in bucket[:6]:
            title = (it.get("service_name")
                     or it.get("question_id") or it.get("request_kind"))
            lines.append(f"- `{it.get('id','?')[:8]}` - {title}"
                          f" ({it.get('criticality','medium')})")
    return lines


def _autonomy_score(blocked_count: int,
                    pending_count: int, total_events: int) -> float:
    """100% = 0 blocked + 0 pending A/B/C + >0 events auto.

    Chaque pending A/B/C compte pour 1 point d'intervention humaine ;
    le score = 1 - interventions / max(total_events, 1).
    """
    interventions = blocked_count + pending_count
    base = max(1, total_events)
    return max(0.0, min(1.0, 1.0 - (interventions / base))) * 100


def _section_autonomy() -> tuple[list[str], float]:
    # Nb d'events dans audit_events (approx du total d'actions systeme)
    audit = fetch("/api/v1/analytics/audit/tail?limit=1") or []
    # On ne peut pas avoir le count exact sans endpoint dedie,
    # on approxime avec les events decrits dans router/history.
    router_hist = fetch("/api/v1/analytics/router/history?limit=100") or []
    evidence_tail = fetch("/api/v1/analytics/evidence/tail?limit=1000") or []
    total_events = max(
        len(router_hist) * 10,  # 1 router decision ~ 10 actions system
        len(evidence_tail),
    )
    inbox = fetch("/api/v1/inbox") or {}
    pending = sum(inbox.get("counts", {}).get(k, 0) for k in ("A", "B", "C"))
    blocked_payload = fetch("/api/v1/inbox/blocked?limit=100") or []
    blocked = len(blocked_payload) if isinstance(blocked_payload, list) else 0
    score = _autonomy_score(blocked, pending, total_events)
    lines = [
        "", "## Niveau d'autonomie", "",
        f"- Score : **{score:.1f}%**",
        f"- Interventions Ahmed en attente : {pending}",
        f"- Demandes hors doctrine bloquees : {blocked}",
        f"- Actions systeme tracees (proxy) : ~{total_events}",
    ]
    return lines, score


def _section_next_improvement() -> list[str]:
    meta = fetch("/api/v1/inbox/meta/latest") or {}
    backlog = fetch("/api/v1/analytics/backlog?status=open&limit=3") or []
    lines = ["", "## Prochaine auto-amelioration", ""]
    if isinstance(backlog, list) and backlog:
        top = backlog[0]
        lines.append(
            f"- **{top.get('priority','medium').upper()}** · "
            f"{top.get('category','?')} : {top.get('title','?')}"
        )
        if len(backlog) > 1:
            lines.append(f"- puis {len(backlog) - 1} autre(s) dans le backlog")
    else:
        lines.append("- Aucun item dans le backlog open.")
    if meta:
        degraded = meta.get("degraded_metrics") or []
        lines.append(
            f"- Dernier snapshot meta : "
            f"{meta.get('projects_last_7d', 0)} projets / 7j, "
            f"rework={float(meta.get('rework_rate', 0))*100:.1f}%, "
            f"degradations={len(degraded)}"
        )
    return lines


def _section_doctrine() -> list[str]:
    return [
        "", "## Doctrine V4.8", "",
        "L'utilisateur n'intervient QUE pour :",
        "- **A** - Ouvrir un compte tiers (email + password)",
        "- **B** - Valider un paiement (lien direct)",
        "- **C** - Clarifier une question metier",
        "",
        "TOUT autre action est executee automatiquement par le systeme "
        "au niveau MIT Senior (selecteurs deterministes, benchmarks, "
        "patterns industriels, tests property-based + chaos, zero trust).",
    ]


def main() -> int:
    print(f"Querying {BACKEND}...")
    lines = ["# UBA Dashboard Readiness", ""]
    lines += [f"_Genere via {BACKEND}_", ""]
    lines += _section_doctrine()
    lines += _section_tools()
    lines += _section_inbox()
    autonomy_lines, score = _section_autonomy()
    lines += autonomy_lines
    lines += _section_next_improvement()
    out = "\n".join(lines) + "\n"
    target = REPO / "dashboard_readiness.md"
    target.write_text(out, encoding="utf-8")
    print(f"wrote {target} ({len(out)} bytes, autonomy={score:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
