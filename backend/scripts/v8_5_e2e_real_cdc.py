"""V8.5F : E2E test reel — soumission d'un CDC mini-market via l'API,
attente de la completion, verification du score V2 + breakdown.

Usage : python backend/scripts/v8_5_e2e_real_cdc.py [--cdc-file path.md]
                                                    [--max-wait 1800]
                                                    [--host http://localhost:8000]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

DEFAULT_HOST = "http://localhost:8000"
DEFAULT_MAX_WAIT_S = 1800

MINI_MARKET_CDC = """# Mini Market — CRUD Produits

## Objectif
API FastAPI pour gerer un catalogue de produits dans un petit commerce.

## Entites
### Produit
- id (int, auto)
- name (str, 1..200)
- price_dzd (Decimal, > 0)
- stock (int, >= 0)
- category (str, 1..50)
- created_at (datetime)

## Endpoints REST
- GET /products            -> liste de tous les produits
- POST /products           -> creer un produit (201)
- GET /products/{id}       -> recuperer un produit (404 si inexistant)
- PUT /products/{id}       -> mettre a jour un produit
- DELETE /products/{id}    -> supprimer un produit (204)
- GET /products/by_category/{cat} -> filtrer par categorie
- GET /health              -> healthcheck

## Regles metier
- price_dzd doit etre strictement positif (validation Pydantic Field gt=0)
- stock doit etre >= 0
- category appartient a {alimentation, boissons, hygiene, autre}

## Tests
- pytest avec fixtures (TestClient, payload sample, store cleanup)
- coverage minimum 70% (vise 80%+)
- tests CRUD complets (POST, GET list, GET one, PUT, DELETE, 404)
- test validation prix negatif -> 422
- test filter by_category

## Livrables
- app/__init__.py, app/main.py, app/models.py, app/store.py
- tests/__init__.py, tests/conftest.py, tests/test_*.py (>= 8 tests)
- requirements.txt (fastapi, uvicorn, pydantic, httpx, pytest, pytest-asyncio,
  pytest-json-report, pytest-cov)
- Dockerfile (python:3.12-slim)
- README.md (Description, Installation, Usage, Tests, Deploy, License,
  exemples curl, env vars)
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--cdc-file", default=None, help="Path vers un .md CDC")
    p.add_argument("--cdc-name", default="mini-market-v8-5f")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--max-wait", type=int, default=DEFAULT_MAX_WAIT_S)
    p.add_argument("--poll-interval", type=int, default=10)
    return p.parse_args()


async def submit_cdc(client: httpx.AsyncClient, cdc_text: str, name: str) -> str:
    payload = {
        "cdc_text": cdc_text,
        "project_name": name,
        "auto_resolve_ambiguities": True,
        "max_duration_minutes": 30,
    }
    r = await client.post("/api/v1/projects/from_cdc", json=payload, timeout=30)
    r.raise_for_status()
    body = r.json()
    print(f"[submit] project_id={body['project_id']} status={body['status']}")
    return body["project_id"]


async def wait_for_completion(
    client: httpx.AsyncClient, project_id: str, max_wait_s: int, poll_interval: int,
) -> dict:
    deadline = time.time() + max_wait_s
    last_status = ""
    while time.time() < deadline:
        try:
            r = await client.get(f"/api/v1/projects/{project_id}/status", timeout=15)
            if r.status_code == 200:
                body = r.json()
                status = body.get("status", "?")
                progress = body.get("progress_percent", 0)
                if status != last_status:
                    print(f"[status] {status} ({progress}%) — {body.get('current_task','')}")
                    last_status = status
                if status in ("delivered", "failed"):
                    return body
        except (httpx.HTTPError, ConnectionError) as exc:
            print(f"[status] poll error: {exc}")
        await asyncio.sleep(poll_interval)
    raise TimeoutError(f"Project {project_id} did not complete within {max_wait_s}s")


async def fetch_validation(client: httpx.AsyncClient, project_id: str) -> dict:
    r = await client.get(f"/api/v1/projects/{project_id}/validation", timeout=15)
    r.raise_for_status()
    return r.json()


async def fetch_quality_gates(client: httpx.AsyncClient, project_id: str) -> dict:
    r = await client.get(f"/api/v1/projects/{project_id}/quality_gates", timeout=15)
    r.raise_for_status()
    return r.json()


async def main() -> int:
    args = parse_args()
    cdc_text = (
        Path(args.cdc_file).read_text(encoding="utf-8")
        if args.cdc_file else MINI_MARKET_CDC
    )

    async with httpx.AsyncClient(base_url=args.host) as client:
        print(f"=== V8.5F E2E real CDC submission @ {args.host} ===")
        project_id = await submit_cdc(client, cdc_text, args.cdc_name)

        try:
            final_status = await wait_for_completion(
                client, project_id, args.max_wait, args.poll_interval,
            )
        except TimeoutError as exc:
            print(f"[TIMEOUT] {exc}")
            return 2

        print(f"\n=== Final status : {final_status['status']} ===")

        try:
            validation = await fetch_validation(client, project_id)
            print("\n=== Validation breakdown V2 ===")
            print(json.dumps(validation, indent=2))
        except httpx.HTTPError as exc:
            print(f"[validation] not available: {exc}")
            validation = {}

        try:
            gates = await fetch_quality_gates(client, project_id)
            print("\n=== Quality gates history ===")
            for g in gates.get("gates", []):
                print(f"  attempt={g['attempt_number']} {g['gate_name']:<14} "
                      f"{g['status']:<6} score={g['score']} ({g['duration_ms']}ms)")
        except httpx.HTTPError as exc:
            print(f"[quality_gates] not available: {exc}")
            gates = {}

        decision = validation.get("decision")
        total = validation.get("total")
        if decision == "ACCEPTED":
            print(f"\n[OK] decision=ACCEPTED total={total}/100 — V8.5F PASS")
            return 0
        if decision == "PARTIAL":
            print(f"\n[PARTIAL] decision=PARTIAL total={total}/100")
            return 1
        print(f"\n[REJECTED] decision={decision} total={total}/100")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
