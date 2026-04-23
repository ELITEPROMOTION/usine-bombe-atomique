"""V5.1 Coverage Audit — genere coverage_audit_v5_1.md.

Classifie chaque fichier app/ en P0/P1/P2/P3, affiche % coverage et
branches manquantes, identifie les trous a combler.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Classification honnete - alignee avec la mission commando
P0 = {
    # Autonomy V5.1 (17+)
    "app/autonomy/": 0.95,
    # Orchestration critique
    "app/orchestration/policy_arbiter.py": 0.95,
    "app/orchestration/evidence_ledger.py": 0.95,
    "app/orchestration/quality_kernel.py": 0.95,
    "app/orchestration/tri_brain.py": 0.95,
    "app/orchestration/decision_router.py": 0.95,
    "app/orchestration/promotion_engine.py": 0.95,
    "app/orchestration/quorum_judge.py": 0.95,
    "app/orchestration/audit_events.py": 0.95,
    "app/orchestration/confidence_scorer.py": 0.95,
    "app/orchestration/dz_rules.py": 0.95,
    "app/middleware/tenant.py": 0.95,
    "app/integrations/vault_client.py": 0.95,
    "app/agents/conformite_dz_agent.py": 0.95,
    "app/inbox/user_interaction_router.py": 0.95,
}

P1 = {
    "app/orchestration/": 0.88,
    "app/agents/": 0.88,
    "app/routers/": 0.85,
    "app/validation/": 0.88,
    "app/intake/": 0.85,
    "app/memory/": 0.85,
    "app/inbox/": 0.88,
}

P2 = {
    "app/orchestration/self_improver.py": 0.75,
    "app/orchestration/auto_tuner.py": 0.75,
    "app/orchestration/cost_optimizer.py": 0.75,
    "app/orchestration/runtime_mesh.py": 0.75,
}


def classify(path: str) -> tuple[str, float]:
    """Retourne (tier, target_coverage) pour un path."""
    p = path.replace("\\", "/")
    for key, target in P0.items():
        if key.endswith("/"):
            if key in p:
                return "P0", target
        elif p.endswith(key):
            return "P0", target
    for key, target in P2.items():
        if p.endswith(key):
            return "P2", target
    for key, target in P1.items():
        if key.endswith("/"):
            if key in p:
                return "P1", target
    return "P3", 0.50


def main() -> None:
    cov = json.loads(Path(ROOT / "cov.json").read_text())
    files = cov["files"]
    total = cov["totals"]

    by_tier: dict[str, list[tuple[str, dict]]] = {"P0": [], "P1": [], "P2": [], "P3": []}
    for path, data in files.items():
        tier, _ = classify(path)
        by_tier[tier].append((path, data))

    lines: list[str] = []
    lines.append("# Coverage Audit V5.1 — Campagne SDET\n")
    lines.append(f"**Global** : {total['percent_covered']:.1f}% "
                 f"({total['covered_lines']}/{total['num_statements']} lignes)\n")
    lines.append(f"**Branches** : {total.get('percent_covered_display', 'n/a')}\n")
    lines.append(f"**Tests** : 227 existants\n\n")

    for tier in ("P0", "P1", "P2", "P3"):
        items = sorted(by_tier[tier], key=lambda x: x[1]["summary"]["percent_covered"])
        if not items:
            continue
        tier_covered = sum(f[1]["summary"]["covered_lines"] for f in items)
        tier_total = sum(f[1]["summary"]["num_statements"] for f in items)
        tier_pct = (tier_covered / tier_total * 100) if tier_total else 0
        lines.append(f"\n## {tier} — {len(items)} fichiers — {tier_pct:.1f}% couvert "
                     f"({tier_covered}/{tier_total})\n")

        # Tableau des fichiers sous la cible
        gaps: list[tuple[str, dict]] = []
        for path, data in items:
            _, target = classify(path)
            pct = data["summary"]["percent_covered"] / 100
            if pct < target:
                gaps.append((path, data))

        if gaps:
            lines.append(f"\n### Gaps {tier} (N={len(gaps)})\n")
            lines.append("| Fichier | % | Lignes manquantes | Branches manquantes |\n")
            lines.append("|---|---|---|---|\n")
            for path, data in gaps[:40]:
                s = data["summary"]
                miss = data.get("missing_lines", [])
                miss_str = ",".join(str(l) for l in miss[:10])
                if len(miss) > 10:
                    miss_str += f" (+{len(miss)-10})"
                miss_b = data.get("missing_branches", [])
                miss_b_str = str(len(miss_b)) if miss_b else "0"
                lines.append(f"| {path} | {s['percent_covered']:.1f}% | {miss_str} | {miss_b_str} |\n")

    out = Path(ROOT / "coverage_audit_v5_1.md")
    out.write_text("".join(lines), encoding="utf-8")
    print(f"wrote {out}")
    print(f"\nTOTAL {total['percent_covered']:.2f}%")
    for tier in ("P0", "P1", "P2", "P3"):
        items = by_tier[tier]
        cov_l = sum(f[1]["summary"]["covered_lines"] for f in items)
        tot_l = sum(f[1]["summary"]["num_statements"] for f in items)
        pct = (cov_l / tot_l * 100) if tot_l else 0
        print(f"  {tier}: {pct:.2f}%  ({cov_l}/{tot_l}, files={len(items)})")


if __name__ == "__main__":
    main()
