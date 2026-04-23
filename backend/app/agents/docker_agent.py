"""Agent #06 Docker - durcit le Dockerfile et ajoute un compose.

Check deterministe sur le Dockerfile existant (si present) :
- HEALTHCHECK   (bonus +0.15)
- USER non-root (bonus +0.20)
- Multi-stage   (bonus +0.15)
- no ADD URL    (-0.10 si present)
- no latest tag image de base (-0.10)

Genere :
- docker-compose.yml (app + postgres + redis) si absent.
- .dockerignore minimaliste si absent.
"""
from __future__ import annotations

import re
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.workspace import Workspace


class DockerAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="agent-06-docker", name="Docker Builder", version="1.0.0")
        self.category = "infrastructure"

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        workspace: Workspace = inputs["workspace"]
        manifest: list[dict[str, Any]] = inputs.get("manifest") or workspace.manifest()
        paths = {str(m["path"]) for m in manifest}
        checks: dict[str, Any] = {}

        dockerfile = _read_if_exists(workspace, "Dockerfile")
        if dockerfile:
            checks.update(_inspect_dockerfile(dockerfile))

        created: list[str] = []
        if "docker-compose.yml" not in paths:
            workspace.write("docker-compose.yml", _compose_template())
            created.append("docker-compose.yml")
        if ".dockerignore" not in paths:
            workspace.write(".dockerignore", _dockerignore())
            created.append(".dockerignore")

        score = _score(checks, bool(dockerfile))
        return {
            "score": round(score, 3),
            "passed": score >= 0.75,
            "dockerfile_present": bool(dockerfile),
            "checks": checks,
            "files_created": created,
        }


def _read_if_exists(ws: Workspace, path: str) -> str | None:
    try:
        return ws.read(path)
    except FileNotFoundError:
        return None


def _inspect_dockerfile(content: str) -> dict[str, Any]:
    has_healthcheck = bool(re.search(r"(?mi)^\s*HEALTHCHECK\b", content))
    has_user = bool(re.search(r"(?mi)^\s*USER\s+(?!root\b)\w+", content))
    stages = len(re.findall(r"(?mi)^\s*FROM\b.*\bAS\b", content))
    multi_stage = stages >= 1
    has_add_url = bool(re.search(r"(?mi)^\s*ADD\s+https?://", content))
    base_latest = bool(re.search(r"(?mi)^\s*FROM\s+\S+:latest\b", content))
    return {
        "has_healthcheck": has_healthcheck,
        "has_non_root_user": has_user,
        "multi_stage": multi_stage,
        "has_add_url": has_add_url,
        "base_latest_tag": base_latest,
    }


SCORE_RULES: tuple[tuple[str, float], ...] = (
    ("has_healthcheck",    +0.15),
    ("has_non_root_user",  +0.20),
    ("multi_stage",        +0.15),
    ("has_add_url",        -0.10),
    ("base_latest_tag",    -0.10),
)


def _score(checks: dict[str, Any], dockerfile_present: bool) -> float:
    if not dockerfile_present:
        return 0.50
    s = 0.50
    for key, delta in SCORE_RULES:
        if checks.get(key):
            s += delta
    return max(0.0, min(1.0, s))


def _compose_template() -> str:
    return """services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://app:app@postgres:5432/app
      REDIS_URL: redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "python -c 'import urllib.request; urllib.request.urlopen(\\"http://localhost:8000/health\\")'"]
      interval: 30s
      timeout: 5s
      retries: 3

  postgres:
    image: postgres:16.4-alpine
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7.4-alpine
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
  redisdata:
"""


def _dockerignore() -> str:
    return """.git
.gitignore
.env
.venv
__pycache__
*.pyc
.pytest_cache
tests/.pytest_report.json
node_modules
.DS_Store
"""
