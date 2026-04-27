"""V8.5 phase E — demonstration end-to-end de validation_score v2.

Lance les 6 quality gates sur un projet existant (par defaut :
generated/dendani-residences) et affiche le breakdown.

Usage :
    python backend/scripts/v8_5_demo_e2e.py
    python backend/scripts/v8_5_demo_e2e.py --path /tmp/some-project
    python backend/scripts/v8_5_demo_e2e.py --json     # output JSON only

Demonstre :
- pytest_agent fallback parser (si pytest-json-report absent)
- 6 gates execution
- score breakdown 100 pts + decision
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Permet l'import quand on lance le script directement depuis backend/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.orchestration.quality_gates import GATE_ORDER, validate_deliverable  # noqa: E402
from app.orchestration.validation_score_v2 import compute_breakdown  # noqa: E402


async def run(project_path: Path, json_only: bool, skip_docker: bool) -> int:
    if not json_only:
        print(f"\n=== V8.5 Quality Gates demo on {project_path} ===\n")
    docker_available = None if not skip_docker else False
    gates_result = await validate_deliverable(
        project_path, docker_available=docker_available, pytest_timeout_s=120,
    )
    breakdown = compute_breakdown(gates_result)
    payload = {
        "project_path": str(project_path),
        "gates": [
            {
                "name": g.name, "status": g.status, "score": g.score,
                "duration_ms": g.duration_ms, "details": g.details,
            }
            for g in gates_result.gates
        ],
        "overall_status": gates_result.overall_status,
        "summary": gates_result.summary,
        "breakdown": breakdown.to_dict(),
    }
    if json_only:
        print(json.dumps(payload, indent=2, default=str))
        return 0 if gates_result.overall_status == "PASS" else 1

    print(f"Overall : {gates_result.overall_status}  ({gates_result.summary})\n")
    print("Gate           | Status | Score | Duration | Details")
    print("-" * 80)
    for name in GATE_ORDER:
        g = next((x for x in gates_result.gates if x.name == name), None)
        if g is None:
            continue
        det = ", ".join(f"{k}={v}" for k, v in list(g.details.items())[:3])
        print(f"{name:<14} | {g.status:<6} | {g.score:>5.2f} | {g.duration_ms:>6} ms | {det[:70]}")

    print("\n=== Validation score v2 (0..100) ===\n")
    print(f"  Decision : {breakdown.decision}")
    print(f"  Total    : {breakdown.total} / {breakdown.to_dict()['scale']}")
    for k, v in breakdown.to_dict()["components"].items():
        print(f"    {k:<14} : {v['score']:>3} / {v['max']:>2}")
    print("\n  Rationale :")
    for r in breakdown.rationale:
        print(f"   - {r}")
    return 0 if breakdown.decision == "ACCEPTED" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        default=str(ROOT.parent / "generated" / "dendani-residences"),
        help="Path to the deliverable to validate (defaults to dendani-residences)",
    )
    parser.add_argument("--json", action="store_true", help="JSON-only output")
    parser.add_argument("--skip-docker", action="store_true",
                        help="Force docker gates to SKIP (useful for fast dev runs)")
    args = parser.parse_args()
    return asyncio.run(run(Path(args.path), args.json, args.skip_docker))


if __name__ == "__main__":
    raise SystemExit(main())
