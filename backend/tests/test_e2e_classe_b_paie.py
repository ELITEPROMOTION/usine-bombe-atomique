"""E2E Classe B : injecte un vrai module Paie DZ puis exerce tout le V2.

Ce test contourne l'agent #01 (Anthropic hors credit). Il seede le workspace
avec un module Paie Algerie correct (CNAS 9/26, IRG bareme 2024, TAP 2),
puis execute les 9 agents post-generation + Tri-Cerveau Critic + Confidence
Scorer. Verifie qu'un Classe B correct obtient un score composite eleve sur
les 6 dimensions, notamment la conformite DZ.
"""
from pathlib import Path

import pytest

from app.agents.conformite_dz_agent import ConformiteDzAgent
from app.agents.datadog_agent import DatadogAgent
from app.agents.docker_agent import DockerAgent
from app.agents.linter_agent import LinterAgent
from app.agents.pytest_agent import PytestAgent
from app.agents.readme_agent import ReadmeAgent
from app.agents.security_agent import SecurityAgent
from app.agents.sonarqube_agent import SonarQubeAgent
from app.agents.terraform_agent import TerraformAgent
from app.agents.workspace import Workspace
from app.orchestration.confidence_scorer import score_confidence
from app.orchestration.tri_brain import _deterministic_critic, _judge
from app.validation.pipeline import run_pipeline


PAIE_FILES: dict[str, str] = {
    "app/__init__.py": '"""Module Paie DZ."""\n',
    "app/business.py": '''"""Regles metier paie Algerie 2024.

Constantes fiscales : TVA 19%, TAP 2%, CNAS salarie 9%, CNAS employeur 26%.
Devise : DZD (Dinar algerien).
"""
from decimal import Decimal, ROUND_HALF_UP

TVA = Decimal("0.19")
TAP = Decimal("0.02")
CNAS_SAL = Decimal("0.09")
CNAS_EMP = Decimal("0.26")
TWO = Decimal("0.01")

# Bareme IRG 2024 (mensuel, Dinar) : (seuil_superieur, taux)
IRG_TRANCHES = [
    (Decimal("30000"),   Decimal("0.00")),
    (Decimal("120000"),  Decimal("0.20")),
    (Decimal("360000"),  Decimal("0.30")),
    (Decimal("1440000"), Decimal("0.35")),
    (Decimal("999999999"), Decimal("0.42")),
]


def valider_nin(nin: str) -> bool:
    """NIN algerien : exactement 18 chiffres."""
    return isinstance(nin, str) and nin.isdigit() and len(nin) == 18


def calculer_cnas_salarie(brut: Decimal) -> Decimal:
    return (brut * CNAS_SAL).quantize(TWO, rounding=ROUND_HALF_UP)


def calculer_cnas_employeur(brut: Decimal) -> Decimal:
    return (brut * CNAS_EMP).quantize(TWO, rounding=ROUND_HALF_UP)


def calculer_tap(brut: Decimal) -> Decimal:
    return (brut * TAP).quantize(TWO, rounding=ROUND_HALF_UP)


def calculer_irg(salaire_imposable: Decimal) -> Decimal:
    restant = salaire_imposable
    prev = Decimal("0")
    irg = Decimal("0")
    for seuil, taux in IRG_TRANCHES:
        if restant <= 0:
            break
        tranche = min(restant, seuil - prev)
        irg += tranche * taux
        prev = seuil
        restant -= tranche
    return irg.quantize(TWO, rounding=ROUND_HALF_UP)


def calculer_net(brut: Decimal, cnas_sal: Decimal, irg: Decimal) -> Decimal:
    return (brut - cnas_sal - irg).quantize(TWO, rounding=ROUND_HALF_UP)
''',
    "app/models.py": '''"""Modeles Pydantic."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field


class Employe(BaseModel):
    id: int
    matricule: str
    nom: str
    prenom: str
    nin: str = Field(min_length=18, max_length=18)
    poste: str
    salaire_base_dzd: Decimal
    date_embauche: datetime
    statut: Literal["actif", "suspendu", "sortant"] = "actif"


class FichePaie(BaseModel):
    id: int
    employe_id: int
    mois: str
    salaire_base: Decimal
    brut: Decimal
    cnas_salarie: Decimal
    cnas_employeur: Decimal
    salaire_imposable: Decimal
    irg: Decimal
    tap_patronal: Decimal
    net_a_payer: Decimal


class Health(BaseModel):
    status: str
    version: str
''',
    "app/main.py": '''"""API Paie Algerie - Groupe Dendani."""
from decimal import Decimal
import logging
from fastapi import FastAPI, HTTPException
from app.business import (
    calculer_cnas_employeur,
    calculer_cnas_salarie,
    calculer_irg,
    calculer_net,
    calculer_tap,
    valider_nin,
)
from app.models import Employe, FichePaie, Health

logger = logging.getLogger(__name__)
app = FastAPI(title="Paie DZ API", description="Module Paie Algerie - DZD")

_employes: dict[int, Employe] = {}
_fiches: dict[int, FichePaie] = {}
_next_emp_id = 1
_next_fiche_id = 1


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", version="1.0.0")


@app.post("/employes", response_model=Employe, status_code=201)
def creer_employe(e: Employe) -> Employe:
    if not valider_nin(e.nin):
        raise HTTPException(422, "NIN invalide (18 chiffres requis)")
    global _next_emp_id
    e.id = _next_emp_id
    _employes[_next_emp_id] = e
    _next_emp_id += 1
    logger.info("Employe cree: matricule=%s", e.matricule)
    return e


@app.get("/employes", response_model=list[Employe])
def lister_employes() -> list[Employe]:
    return list(_employes.values())


@app.post("/paie/generer", response_model=list[FichePaie])
def generer_paie(mois: str) -> list[FichePaie]:
    global _next_fiche_id
    fiches: list[FichePaie] = []
    for emp in _employes.values():
        if emp.statut != "actif":
            continue
        brut = emp.salaire_base_dzd
        cnas_sal = calculer_cnas_salarie(brut)
        cnas_emp = calculer_cnas_employeur(brut)
        imposable = brut - cnas_sal
        irg = calculer_irg(imposable)
        tap = calculer_tap(brut)
        net = calculer_net(brut, cnas_sal, irg)
        fiche = FichePaie(
            id=_next_fiche_id, employe_id=emp.id, mois=mois,
            salaire_base=brut, brut=brut,
            cnas_salarie=cnas_sal, cnas_employeur=cnas_emp,
            salaire_imposable=imposable, irg=irg,
            tap_patronal=tap, net_a_payer=net,
        )
        _fiches[_next_fiche_id] = fiche
        _next_fiche_id += 1
        fiches.append(fiche)
    return fiches


@app.get("/paie/g50", response_model=dict)
def declaration_g50(mois: str) -> dict:
    total_cnas_sal = sum((f.cnas_salarie for f in _fiches.values() if f.mois == mois), Decimal("0"))
    total_cnas_emp = sum((f.cnas_employeur for f in _fiches.values() if f.mois == mois), Decimal("0"))
    total_irg = sum((f.irg for f in _fiches.values() if f.mois == mois), Decimal("0"))
    total_tap = sum((f.tap_patronal for f in _fiches.values() if f.mois == mois), Decimal("0"))
    return {
        "mois": mois,
        "total_cnas_salarie": str(total_cnas_sal),
        "total_cnas_employeur": str(total_cnas_emp),
        "total_irg": str(total_irg),
        "total_tap": str(total_tap),
        "total_a_verser": str(total_cnas_sal + total_cnas_emp + total_irg + total_tap),
    }
''',
    "Dockerfile": '''FROM python:3.12-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
RUN useradd -r -u 10001 app
WORKDIR /app
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY app ./app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
''',
    "requirements.txt": '''fastapi==0.115.0
uvicorn[standard]==0.32.0
pydantic==2.9.2
httpx==0.27.2
pytest==8.3.3
''',
    "pytest.ini": "[pytest]\naddopts = -ra --strict-markers\ntestpaths = tests\n",
    "README.md": '''# Module Paie Algerie

Genere par UBA V2. Conformite fiscale algerienne : **TVA 19%**, **TAP 2%**,
**CNAS 9% salarie / 26% employeur**, **IRG bareme progressif 2024** (tranches 30000,
120000, 360000, 1440000). Devise **DZD**. NIN valide (18 chiffres).

## Endpoints
- `GET  /health`
- `CRUD /employes` (POST, GET)
- `POST /paie/generer?mois=YYYY-MM`
- `GET  /paie/g50?mois=YYYY-MM`

## Exemples
```bash
curl -X POST http://localhost:8000/employes -H "Content-Type: application/json" \
  -d '{"id":0,"matricule":"E001","nom":"Benali","prenom":"Amine",
       "nin":"123456789012345678","poste":"Developpeur",
       "salaire_base_dzd":"150000","date_embauche":"2024-01-01"}'
curl -X POST "http://localhost:8000/paie/generer?mois=2026-04"
curl "http://localhost:8000/paie/g50?mois=2026-04"
```

## Conformite DZ
- Bareme IRG 2024 complet
- CNAS salarie 9%, employeur 26%
- TAP patronal 2% sur brut
- NIN 18 chiffres valide
''',
    "tests/__init__.py": "",
    "tests/test_business.py": '''"""Tests metier paie DZ."""
from decimal import Decimal
from app.business import (
    calculer_cnas_employeur, calculer_cnas_salarie, calculer_irg,
    calculer_net, calculer_tap, valider_nin,
)


def test_cnas_salarie_9_pourcent():
    assert calculer_cnas_salarie(Decimal("100000")) == Decimal("9000.00")


def test_cnas_employeur_26_pourcent():
    assert calculer_cnas_employeur(Decimal("100000")) == Decimal("26000.00")


def test_tap_2_pourcent():
    assert calculer_tap(Decimal("100000")) == Decimal("2000.00")


def test_nin_valide_et_invalide():
    assert valider_nin("123456789012345678") is True
    assert valider_nin("12345") is False
    assert valider_nin("abcdefghij12345678") is False


def test_irg_tranche_1_nulle():
    assert calculer_irg(Decimal("30000")) == Decimal("0.00")


def test_irg_tranche_2_20_pct():
    # 90000 dans la tranche 2 a 20%
    assert calculer_irg(Decimal("120000")) == Decimal("18000.00")


def test_irg_progressif_400000():
    # 30000*0 + 90000*0.20 + 240000*0.30 + 40000*0.35
    # = 0 + 18000 + 72000 + 14000 = 104000
    assert calculer_irg(Decimal("400000")) == Decimal("104000.00")


def test_net_a_payer():
    brut = Decimal("150000")
    cnas = calculer_cnas_salarie(brut)  # 13500
    imposable = brut - cnas              # 136500
    irg = calculer_irg(imposable)        # 18000 + 4950 = 22950
    assert irg == Decimal("22950.00")
    assert calculer_net(brut, cnas, irg) == Decimal("113550.00")
''',
    "tests/test_api.py": '''"""Tests API Paie."""
from decimal import Decimal
from fastapi.testclient import TestClient
from app.main import app


def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_creer_employe_et_generer_paie():
    client = TestClient(app)
    payload = {
        "id": 0, "matricule": "E100", "nom": "Test", "prenom": "Paie",
        "nin": "111222333444555666", "poste": "QA",
        "salaire_base_dzd": "150000", "date_embauche": "2024-01-01",
    }
    r = client.post("/employes", json=payload)
    assert r.status_code == 201
    r = client.post("/paie/generer?mois=2026-04")
    assert r.status_code == 200
    fiches = r.json()
    assert len(fiches) >= 1
    assert Decimal(fiches[-1]["cnas_salarie"]) == Decimal("13500.00")


def test_nin_invalide_rejet():
    client = TestClient(app)
    r = client.post("/employes", json={
        "id": 0, "matricule": "E200", "nom": "X", "prenom": "Y",
        "nin": "short", "poste": "Z",
        "salaire_base_dzd": "100000", "date_embauche": "2024-01-01",
    })
    assert r.status_code == 422
''',
}


@pytest.mark.asyncio
async def test_classe_b_paie_dz_full_v2_pipeline(tmp_path: Path):
    """Execute les 9 agents post-generation + Critic + Confidence sur un vrai module Paie."""
    import shutil
    tools = ("ruff", "bandit", "radon", "pytest")
    if not all(shutil.which(t) for t in tools):
        pytest.skip(f"outils CLI requis: {tools}")

    ws = Workspace.create(task_id="classe-b-paie", root=tmp_path)
    for path, content in PAIE_FILES.items():
        ws.write(path, content)
    spec = "Module Paie Algerie : CNAS 9% et 26%, IRG bareme 2024, TAP 2%, TVA 19%, NIN 18 chiffres, devise DZD"

    # Tri-Cerveau Critic (deterministe)
    issues = _deterministic_critic(ws.files)
    decision = _judge(issues)
    assert decision.verdict in ("approve", "refine"), decision

    # Execute les 9 agents V2 sequentiellement (simulation DAG)
    manifest = ws.manifest()
    inputs = {"workspace": ws, "spec": spec, "manifest": manifest}
    results = {}
    for agent_cls in [LinterAgent, SonarQubeAgent, PytestAgent, TerraformAgent,
                      DockerAgent, ConformiteDzAgent, SecurityAgent,
                      DatadogAgent, ReadmeAgent]:
        agent = agent_cls()
        res = await agent.execute({**inputs, "manifest": ws.manifest()})
        assert res.status == "success", f"{agent.agent_id} failed: {res.error}"
        results[agent.agent_id] = res

    # Pipeline validation 5 niveaux
    pipeline = await run_pipeline({"workspace": ws, "agents": results, "manifest": ws.manifest()})
    assert pipeline.verdict in ("PASS", "CONDITIONAL_PASS"), pipeline.verdict

    # DZ agent doit reconnaitre le domaine paie et scorer haut
    dz_output = results["agent-18-conformite-dz"].output
    assert dz_output["domain"]["paie"] is True
    assert dz_output["score"] >= 0.75, dz_output

    # Security + Tests OK
    assert results["agent-04-pytest"].output["passed"] is True
    assert results["agent-11-security"].output["passed"] is True

    # Confidence scorer : 6 dimensions
    confidence = score_confidence(
        manifest=ws.manifest(),
        agent_results=results,
        validation_levels=[{"level": lv.level, "score": lv.score, "passed": lv.passed}
                           for lv in pipeline.levels],
    )
    assert confidence.composite >= 0.85, confidence.to_dict()
    assert confidence.label in ("high", "very_high"), confidence.label
    dims = {d.name: d.score for d in confidence.dimensions}
    assert dims["conformity"] >= 0.80, f"conformity too low: {dims['conformity']}"
    assert dims["correctness"] == 1.0
