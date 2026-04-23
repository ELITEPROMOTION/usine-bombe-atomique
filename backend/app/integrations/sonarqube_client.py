"""SonarQube REST API client (Community Edition, self-hosted port 9000).

Fallback gracieux : si SonarQube n'est pas joignable, l'agent #02 retombe
sur l'analyse locale (bandit+radon) deja implementee en V1.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_URL = os.environ.get("SONAR_HOST_URL", "http://sonarqube:9000")


class SonarQubeClient:
    def __init__(
        self,
        host: str | None = None,
        token: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.host = (host or DEFAULT_URL).rstrip("/")
        self.token = token or os.environ.get("SONAR_TOKEN", "")
        self._timeout = timeout

    def _auth(self) -> tuple[str, str] | None:
        return (self.token, "") if self.token else None

    async def health(self) -> dict[str, Any]:
        """Retourne {"status": "UP"|"DOWN"|"unreachable"}."""
        url = f"{self.host}/api/system/status"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                r = await c.get(url)
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            logger.debug("sonarqube health unreachable: %s", exc)
            return {"status": "unreachable", "error": str(exc)}

    async def ensure_project(self, project_key: str, name: str | None = None) -> bool:
        """Cree le projet s'il n'existe pas. Requiert un token admin."""
        auth = self._auth()
        if not auth:
            return False
        try:
            async with httpx.AsyncClient(timeout=self._timeout, auth=auth) as c:
                # search
                r = await c.get(f"{self.host}/api/projects/search",
                                 params={"projects": project_key})
                if r.status_code == 200 and r.json().get("components"):
                    return True
                # create
                cr = await c.post(f"{self.host}/api/projects/create",
                                   params={"project": project_key,
                                           "name": name or project_key})
                return cr.status_code in (200, 204)
        except Exception as exc:
            logger.warning("sonarqube ensure_project failed: %s", exc)
            return False

    async def measures(self, project_key: str) -> dict[str, float]:
        """Retourne les metriques cles du projet (bugs, vulnerabilities, sqale, coverage)."""
        auth = self._auth()
        metric_keys = "bugs,vulnerabilities,code_smells,sqale_rating,coverage,ncloc"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, auth=auth) as c:
                r = await c.get(
                    f"{self.host}/api/measures/component",
                    params={"component": project_key, "metricKeys": metric_keys},
                )
                r.raise_for_status()
                data = r.json()
        except Exception as exc:
            logger.debug("sonarqube measures miss: %s", exc)
            return {}
        out: dict[str, float] = {}
        for m in data.get("component", {}).get("measures", []):
            try:
                out[m["metric"]] = float(m["value"])
            except (KeyError, TypeError, ValueError):
                continue
        return out


def score_from_measures(measures: dict[str, float]) -> float:
    """Pondere bugs/vulnerabilities/code_smells en un score 0..1."""
    if not measures:
        return 0.0
    bugs = measures.get("bugs", 0)
    vuln = measures.get("vulnerabilities", 0)
    smells = measures.get("code_smells", 0)
    cov = measures.get("coverage", 0)  # 0..100
    # Penalites
    score = 1.0
    score -= 0.10 * min(5, vuln)
    score -= 0.05 * min(5, bugs)
    score -= 0.01 * min(20, smells)
    score += (cov / 100.0) * 0.10  # bonus couverture
    return max(0.0, min(1.0, score))
