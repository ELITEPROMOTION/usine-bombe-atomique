"""Moteur de progression : calcule le pourcentage d'avancement d'un projet.

Modele simple : le projet traverse des phases ponderees (poids defini par
le pack). Chaque phase a un statut (PENDING / IN_PROGRESS / DONE) et un
sous-pourcentage [0..100] quand IN_PROGRESS.

Le pourcentage global se calcule comme :
    overall = sum(phase.weight * phase.completion / 100)

Le paywall se declenche a `PAYWALL_THRESHOLD_PCT` (20% par CDC). Le moteur
expose `is_at_paywall()` que l'orchestrateur appelle pour decider de bloquer
ou non la suite du pipeline en attendant le paiement.

Pas de WebSocket cote moteur : il calcule, c'est tout. Le pousher
real-time vers le client est un job separe (Phase 9M dashboard ou Arq).
"""
from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

import asyncpg

logger = logging.getLogger(__name__)


# CDC : "Validation 20% -> Paiement Integral"
PAYWALL_THRESHOLD_PCT: Final[float] = 20.0


class ProjectPhase(str, enum.Enum):
    ANALYSIS = "ANALYSIS"
    DESIGN = "DESIGN"
    CORE = "CORE"
    FEATURES = "FEATURES"
    TESTING = "TESTING"
    DEPLOY = "DEPLOY"


PROGRESSION_PHASES: tuple[ProjectPhase, ...] = (
    ProjectPhase.ANALYSIS,
    ProjectPhase.DESIGN,
    ProjectPhase.CORE,
    ProjectPhase.FEATURES,
    ProjectPhase.TESTING,
    ProjectPhase.DEPLOY,
)


class PhaseStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


@dataclass(frozen=True)
class PhaseState:
    phase: ProjectPhase
    weight_pct: int
    status: PhaseStatus
    completion_pct: int          # [0..100] dans la phase courante uniquement
    started_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True)
class ProgressionSnapshot:
    project_id: str
    overall_pct: float            # [0..100]
    current_phase: ProjectPhase
    phases: tuple[PhaseState, ...]
    is_at_paywall: bool
    paywall_triggered_at: datetime | None
    eta_completion: datetime | None
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _compute_overall(phases: tuple[PhaseState, ...]) -> float:
    total = 0.0
    for ps in phases:
        if ps.status is PhaseStatus.DONE:
            total += float(ps.weight_pct)
        elif ps.status is PhaseStatus.IN_PROGRESS:
            total += ps.weight_pct * (ps.completion_pct / 100.0)
    return min(100.0, max(0.0, total))


def _current_phase(phases: tuple[PhaseState, ...]) -> ProjectPhase:
    for ps in phases:
        if ps.status is PhaseStatus.IN_PROGRESS:
            return ps.phase
    # Sinon, premier PENDING ; sinon, dernier DONE.
    for ps in phases:
        if ps.status is PhaseStatus.PENDING:
            return ps.phase
    return phases[-1].phase


def _eta(phases: tuple[PhaseState, ...], now: datetime) -> datetime | None:
    """ETA naive : projete a partir du rythme actuel des phases DONE."""
    done_with_times = [
        ps for ps in phases
        if ps.status is PhaseStatus.DONE
        and ps.started_at is not None and ps.completed_at is not None
    ]
    if not done_with_times:
        return None
    # Vitesse moyenne : poids termine / duree cumulee
    total_done_weight = sum(ps.weight_pct for ps in done_with_times)
    total_duration = sum(
        ((ps.completed_at - ps.started_at).total_seconds()  # type: ignore[operator]
         for ps in done_with_times),
        start=0.0,
    )
    if total_duration <= 0 or total_done_weight <= 0:
        return None
    seconds_per_pct = total_duration / total_done_weight
    overall = _compute_overall(phases)
    remaining_pct = 100.0 - overall
    if remaining_pct <= 0:
        return now
    return now + timedelta(seconds=remaining_pct * seconds_per_pct)


class ProgressionEngine:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def initialize(
        self,
        *,
        project_id: str,
        pack_phase_weights: dict[str, int],
    ) -> None:
        """Insere les 6 lignes (1 par phase) avec status=pending et 0%."""
        if set(pack_phase_weights) != {p.value for p in PROGRESSION_PHASES}:
            raise ValueError(
                f"pack_phase_weights doit contenir exactement {sorted(p.value for p in PROGRESSION_PHASES)}"
            )
        if sum(pack_phase_weights.values()) != 100:
            raise ValueError("pack_phase_weights doit sommer a 100")

        rows = [
            (project_id, p.value, pack_phase_weights[p.value])
            for p in PROGRESSION_PHASES
        ]
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO project_progression
                    (project_id, phase, weight_pct, status, completion_pct)
                VALUES ($1, $2, $3, 'pending', 0)
                ON CONFLICT (project_id, phase) DO NOTHING
                """,
                rows,
            )
        logger.info("progression.initialized project=%s", project_id)

    async def update_phase(
        self,
        *,
        project_id: str,
        phase: ProjectPhase,
        status: PhaseStatus,
        completion_pct: int = 0,
    ) -> None:
        if not 0 <= completion_pct <= 100:
            raise ValueError(f"completion_pct hors bornes: {completion_pct}")

        if status is PhaseStatus.DONE:
            completion_pct = 100

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE project_progression
                   SET status = $3,
                       completion_pct = $4,
                       started_at = COALESCE(started_at,
                           CASE WHEN $3 IN ('in_progress','done') THEN NOW() END),
                       completed_at = CASE WHEN $3 = 'done' THEN NOW()
                                            ELSE completed_at END,
                       updated_at = NOW()
                 WHERE project_id = $1 AND phase = $2
                """,
                project_id, phase.value, status.value, completion_pct,
            )

    async def snapshot(self, project_id: str) -> ProgressionSnapshot:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT phase, weight_pct, status, completion_pct,
                       started_at, completed_at, paywall_triggered_at
                  FROM project_progression
                 WHERE project_id = $1
                 ORDER BY array_position(
                     ARRAY['ANALYSIS','DESIGN','CORE','FEATURES','TESTING','DEPLOY'],
                     phase
                 )
                """,
                project_id,
            )
        if not rows:
            raise LookupError(f"progression introuvable pour project={project_id!r}")

        phases = tuple(
            PhaseState(
                phase=ProjectPhase(r["phase"]),
                weight_pct=r["weight_pct"],
                status=PhaseStatus(r["status"]),
                completion_pct=r["completion_pct"],
                started_at=r["started_at"],
                completed_at=r["completed_at"],
            )
            for r in rows
        )
        overall = _compute_overall(phases)
        is_paywall = overall >= PAYWALL_THRESHOLD_PCT
        # paywall_triggered_at provient de la 1ere ligne (toutes le partagent).
        paywall_triggered_at = rows[0]["paywall_triggered_at"]
        if is_paywall and paywall_triggered_at is None:
            now = datetime.now(UTC)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE project_progression
                       SET paywall_triggered_at = $2
                     WHERE project_id = $1 AND paywall_triggered_at IS NULL
                    """,
                    project_id, now,
                )
            paywall_triggered_at = now

        now = datetime.now(UTC)
        return ProgressionSnapshot(
            project_id=project_id,
            overall_pct=overall,
            current_phase=_current_phase(phases),
            phases=phases,
            is_at_paywall=is_paywall,
            paywall_triggered_at=paywall_triggered_at,
            eta_completion=_eta(phases, now),
        )

    @staticmethod
    def to_websocket_payload(snap: ProgressionSnapshot) -> dict:
        """Format JSON-serialisable pour push WebSocket (a brancher en 9M)."""
        return {
            "project_id": snap.project_id,
            "overall_pct": round(snap.overall_pct, 1),
            "current_phase": snap.current_phase.value,
            "is_at_paywall": snap.is_at_paywall,
            "paywall_triggered_at": (
                snap.paywall_triggered_at.isoformat()
                if snap.paywall_triggered_at else None
            ),
            "eta_completion": (
                snap.eta_completion.isoformat() if snap.eta_completion else None
            ),
            "phases": [
                {
                    "phase": ps.phase.value,
                    "weight_pct": ps.weight_pct,
                    "status": ps.status.value,
                    "completion_pct": ps.completion_pct,
                }
                for ps in snap.phases
            ],
            "captured_at": snap.captured_at.isoformat(),
        }


# `json` import kept top-level for symmetry with other engines (used in
# upstream callers via to_websocket_payload).
_ = json
