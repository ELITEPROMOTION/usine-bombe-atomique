"""V7 E2E — pipeline 'CDC -> Livrable' bout-en-bout.

Exige une stack UBA running (docker compose up -d). Designe pour s'executer en
ligne de commande sur la machine du dev :

    docker compose exec -e E2E_REAL=1 backend pytest \
        tests/e2e/test_real_cdc_pipeline.py -v

Skip automatique en CI (pas de E2E_REAL=1 et pas de stack disponible).
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import zipfile
from pathlib import Path

import httpx
import pytest

E2E_BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
E2E_AHMED_EMAIL = os.getenv("E2E_AHMED_EMAIL", "ahmed@dendani.dz")
E2E_AHMED_PASSWORD = os.getenv("E2E_AHMED_PASSWORD", "V7TestPass2026!")
E2E_TIMEOUT_SECONDS = int(os.getenv("E2E_TIMEOUT_SECONDS", "1800"))
E2E_POLL_INTERVAL = float(os.getenv("E2E_POLL_INTERVAL_S", "10"))

CDC_PATH_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "cdc_examples" / "cdc_dendani_residences_v1.md",
    Path("/app/cdc_examples/cdc_dendani_residences_v1.md"),
    Path("/repo/backend/cdc_examples/cdc_dendani_residences_v1.md"),
]


def _read_cdc() -> str:
    for p in CDC_PATH_CANDIDATES:
        if p.exists():
            return p.read_text(encoding="utf-8")
    raise FileNotFoundError(f"CDC introuvable parmi : {CDC_PATH_CANDIDATES}")


pytestmark = pytest.mark.skipif(
    os.getenv("E2E_REAL") != "1",
    reason="Set E2E_REAL=1 pour activer l'execution reelle (skipped par defaut)",
)


@pytest.mark.asyncio
@pytest.mark.timeout(E2E_TIMEOUT_SECONDS + 60)
async def test_submit_real_cdc_dendani_residences():
    cdc_text = _read_cdc()
    assert len(cdc_text) > 200, f"CDC trop court : {len(cdc_text)} chars"

    async with httpx.AsyncClient(base_url=E2E_BASE_URL, timeout=30.0) as client:
        # 1. Login
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": E2E_AHMED_EMAIL, "password": E2E_AHMED_PASSWORD},
        )
        if login.status_code == 401:
            await client.post(
                "/api/v1/auth/register",
                json={
                    "email": E2E_AHMED_EMAIL,
                    "password": E2E_AHMED_PASSWORD,
                    "full_name": "Ahmed Dendani",
                },
            )
            login = await client.post(
                "/api/v1/auth/login",
                json={"email": E2E_AHMED_EMAIL, "password": E2E_AHMED_PASSWORD},
            )
        assert login.status_code == 200, f"Login fail : {login.status_code} {login.text[:200]}"
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Submit project from CDC
        submit = await client.post(
            "/api/v1/projects/from_cdc",
            headers=headers,
            json={
                "cdc_text": cdc_text,
                "project_name": "dendani-residences-v1",
                "tenant_id": "dendani",
                "auto_resolve_ambiguities": True,
                "max_duration_minutes": 30,
            },
        )
        assert submit.status_code in (200, 201), \
            f"Submit fail : {submit.status_code} {submit.text[:300]}"
        body = submit.json()
        project_id = body["project_id"]
        print(f"[V7] project submitted : {project_id} (initial status={body['status']})")

        # 3. Poll status
        loop = asyncio.get_event_loop()
        start = loop.time()
        last_status = ""
        while True:
            elapsed = loop.time() - start
            if elapsed > E2E_TIMEOUT_SECONDS:
                pytest.fail(f"Timeout {E2E_TIMEOUT_SECONDS}s atteint sans 'delivered' (last={last_status})")
            status_resp = await client.get(
                f"/api/v1/projects/{project_id}/status",
                headers=headers,
            )
            assert status_resp.status_code == 200, status_resp.text[:300]
            s = status_resp.json()
            if s["status"] != last_status:
                print(f"[V7] {int(elapsed)}s : status={s['status']} progress={s.get('progress_percent')}% current={s.get('current_task')}")
                last_status = s["status"]
            if s["status"] == "delivered":
                break
            if s["status"] == "failed":
                pytest.fail(f"Pipeline failed : {s.get('error', 'unknown')}")
            await asyncio.sleep(E2E_POLL_INTERVAL)

        # 4. Download deliverable
        deliv = await client.get(
            f"/api/v1/projects/{project_id}/deliverable",
            headers=headers,
        )
        assert deliv.status_code == 200, f"Download fail : {deliv.status_code}"
        ctype = deliv.headers.get("content-type", "")
        assert "application/zip" in ctype or "octet-stream" in ctype, ctype

        # 5. Extract + minimum invariants
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "deliverable.zip"
            zip_path.write_bytes(deliv.content)
            extract_dir = Path(tmpdir) / "extracted"
            extract_dir.mkdir()
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)

            entries = list(extract_dir.rglob("*"))
            files = [p for p in entries if p.is_file()]
            assert files, "ZIP livrable est vide"

            names_lower = [p.name.lower() for p in files]
            print(f"[V7] livrable contient {len(files)} fichiers")
            print(f"[V7] sample : {names_lower[:10]}")

            # Pas d'invariant strict sur Dockerfile/README (depend pipeline existant) :
            # on verifie au moins qu'on a des artefacts non-vides pertinents.
            non_empty = [p for p in files if p.stat().st_size > 0]
            assert non_empty, "Tous les fichiers du livrable sont vides"

        print(f"[V7] PASS — projet {project_id} livre avec {len(files)} fichiers")
