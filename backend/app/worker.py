"""Worker Arq - pipeline V3 : DAG + validation + confidence + memoire apprenante."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, ClassVar
from uuid import UUID

from arq.connections import RedisSettings

from app.agents.base_agent import AgentResult
from app.agents.registry import AgentRegistry
from app.agents.workspace import Workspace
from app.config import get_settings
from app.database import close_pool, get_pool, init_pool
from app.orchestration import (
    auto_repair,
    decision_router,
    evidence_ledger,
    marketplace,
    promotion_engine,
    self_improver,
)
from app.orchestration.auto_tuner import Thresholds, load_thresholds, retune_global
from app.orchestration.confidence_report import classify_manifest
from app.orchestration.confidence_scorer import ConfidenceReport, score_confidence
from app.orchestration.cost_optimizer import total_cost_for_task
from app.orchestration.memory_engine import (
    ProjectRecord,
    classify_error,
    extract_domain_tags,
    record_error,
    record_project,
    sanitize_spec,
    update_agent_benchmark,
)
from app.orchestration.quality_gates import (
    QualityGatesEngine,
    persist_results as persist_gates_results,
)
from app.orchestration.validation_score_v2 import compute_breakdown
from app.orchestrator import OrchestrationResult, run_dag
from app.validation.level_zero import validate as validate_level_zero
from app.validation.pipeline import LEVEL_NAMES, PipelineResult, run_pipeline

logger = logging.getLogger(__name__)
settings = get_settings()


# --------------------------------------------------------------------------- helpers

async def _load_task(pool: Any, task_uuid: UUID) -> tuple[str, str]:
    """Charge la spec + priority et passe en status='executing'."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT prompt, priority FROM tasks WHERE id = $1", task_uuid,
        )
        if not row:
            raise RuntimeError(f"Task {task_uuid} not found")
        await conn.execute(
            "UPDATE tasks SET status='executing', started_at=NOW() WHERE id=$1",
            task_uuid,
        )
    return row["prompt"], row["priority"] or "high"


async def _persist_results(
    pool: Any,
    task_uuid: UUID,
    orchestration: OrchestrationResult,
    pipeline_result: PipelineResult,
    confidence: ConfidenceReport,
    workspace: Workspace,
    manifest: list[dict[str, Any]],
) -> None:
    """Ecrit agent_executions, validation_logs, artifacts, status final."""
    async with pool.acquire() as conn, conn.transaction():
        for agent_id, result in orchestration.results.items():
            await conn.execute(
                """
                INSERT INTO agent_executions
                    (task_id, agent_id, agent_name, status, output_json,
                     error_message, duration_ms, started_at, completed_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, NOW(), NOW())
                """,
                task_uuid, agent_id, result.agent_name, result.status,
                json.dumps(result.output), result.error, result.duration_ms,
            )
        for lvl in pipeline_result.levels:
            await conn.execute(
                """
                INSERT INTO validation_logs
                    (task_id, level_number, level_name, score, passed,
                     details, issues_json)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                task_uuid, lvl.level, LEVEL_NAMES[lvl.level], lvl.score,
                lvl.passed, lvl.details, json.dumps(lvl.issues or []),
            )
        for meta in manifest:
            content = workspace.read(str(meta["path"]))
            await conn.execute(
                """
                INSERT INTO artifacts
                    (task_id, filename, path, type, language, size_bytes,
                     checksum_sha256, content)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                task_uuid, str(meta["path"]).split("/")[-1],
                str(meta["path"]), str(meta["type"]), str(meta["language"]),
                int(meta["size_bytes"]), str(meta["sha256"]), content,
            )
        final_status = (
            "completed" if pipeline_result.verdict in ("PASS", "CONDITIONAL_PASS")
            else "failed"
        )
        await conn.execute(
            """
            UPDATE tasks
            SET status=$2, completed_at=NOW(),
                validation_score=$3, plan_json=$4::jsonb
            WHERE id=$1
            """,
            task_uuid, final_status, pipeline_result.global_score,
            json.dumps({"confidence": confidence.to_dict()}),
        )


async def _update_learning_memory(
    pool: Any,
    task_id: str,
    spec: str,
    orchestration: OrchestrationResult,
    pipeline_result: PipelineResult,
    confidence: ConfidenceReport,
    manifest_size: int,
    total_cost: float,
    duration_ms: int,
) -> None:
    """V3 : alimente project_memory + agent_benchmarks + error_catalog."""
    try:
        await record_project(pool, ProjectRecord(
            task_id=task_id,
            spec_excerpt=sanitize_spec(spec),
            domain_tags=extract_domain_tags(spec),
            artifacts_count=manifest_size,
            verdict=pipeline_result.verdict,
            validation_score=pipeline_result.global_score,
            confidence_composite=confidence.composite,
            confidence_label=confidence.label,
            total_cost_usd=total_cost,
            duration_ms=duration_ms,
        ))
    except Exception as exc:
        logger.warning("record_project failed: %s", exc)

    for agent_id, result in orchestration.results.items():
        await _record_single_agent(pool, agent_id, result)


async def _record_single_agent(pool: Any, agent_id: str, result: AgentResult) -> None:
    score_val: float | None = None
    if result.output and isinstance(result.output.get("score"), int | float):
        score_val = float(result.output["score"])
    try:
        await update_agent_benchmark(
            pool,
            agent_id=agent_id,
            agent_name=result.agent_name,
            status=result.status,
            duration_ms=result.duration_ms,
            score=score_val,
            cost_usd=0.0,
        )
    except Exception as exc:
        logger.warning("update_agent_benchmark %s failed: %s", agent_id, exc)
    if result.status == "failed" and result.error:
        try:
            await record_error(pool, agent_id,
                               classify_error(result.error), result.error)
        except Exception as exc:
            logger.warning("record_error %s failed: %s", agent_id, exc)


async def _run_auto_optim(pool: Any) -> None:
    """V4 + V4.1 : retune thresholds, marketplace, self-improver, auto-repair."""
    try:
        await retune_global(pool)
    except Exception as exc:
        logger.warning("auto_tuner retune failed: %s", exc)
    try:
        await marketplace.refresh_marketplace(pool)
    except Exception as exc:
        logger.warning("marketplace refresh failed: %s", exc)
    try:
        cycle = await self_improver.run_cycle(pool)
        logger.info("self_improver : %d propositions persistees", cycle["persisted"])
    except Exception as exc:
        logger.warning("self_improver failed: %s", exc)
    try:
        repair = await auto_repair.run_cycle(pool)
        logger.info("auto_repair : %d anomalies detectees", repair["anomalies_count"])
    except Exception as exc:
        logger.warning("auto_repair cycle failed: %s", exc)


def _build_pipeline_inputs(
    workspace: Workspace,
    orchestration: OrchestrationResult,
    manifest: list[dict[str, Any]],
    thresholds: Thresholds,
) -> dict[str, Any]:
    return {
        "workspace": workspace,
        "agents": orchestration.results,
        "manifest": manifest,
        "thresholds": {
            "pass_min": thresholds.pass_min,
            "cpass_min": thresholds.cpass_min,
        },
    }


# --------------------------------------------------------------------------- run_task helpers

async def _run_level_zero(pool: Any, workspace: Workspace, manifest: list[dict[str, Any]],
                            task_id: str) -> None:
    """Execute level_zero structural validation + logue preuve si echec."""
    files_map: dict[str, str] = {
        str(m["path"]): workspace.read(str(m["path"])) for m in manifest
    }
    level_zero = validate_level_zero(files_map)
    if level_zero.passed:
        return
    logger.warning("level_zero FAILED : %d issues", len(level_zero.issues))
    try:
        await evidence_ledger.record(
            pool, kind="test", actor="level_zero_validator",
            payload={"passed": False, "issues": level_zero.issues[:10]},
            task_id=task_id,
        )
    except Exception as exc:
        logger.warning("level_zero evidence failed: %s", exc)


async def _run_validation_and_confidence(
    pool: Any, workspace: Workspace, orchestration: OrchestrationResult,
    manifest: list[dict[str, Any]],
) -> tuple[PipelineResult, ConfidenceReport, Thresholds]:
    """Execute pipeline validation + score confidence."""
    artifact_confidence = classify_manifest(workspace, manifest)
    if artifact_confidence["block"]:
        logger.warning("artifact_confidence BLOCK : %d contradictions",
                       artifact_confidence["assertions_contradictory"])
    thresholds = await load_thresholds(pool, scope="global")
    pipeline_result = await run_pipeline(
        _build_pipeline_inputs(workspace, orchestration, manifest, thresholds),
    )
    confidence = score_confidence(
        manifest=manifest,
        agent_results=orchestration.results,
        validation_levels=[
            {"level": lvl.level, "score": lvl.score, "passed": lvl.passed}
            for lvl in pipeline_result.levels
        ],
    )
    logger.info("confidence composite=%.3f label=%s",
                confidence.composite, confidence.label)
    return pipeline_result, confidence, thresholds


async def _run_decision_router_and_promotion(
    pool: Any, task_id: str, pipeline_result: PipelineResult,
    confidence: ConfidenceReport, orchestration: OrchestrationResult,
    artifact_version: str,
) -> tuple[Any, list[dict[str, Any]]]:
    """Route decision + pipeline promotion ou rollback selon verdict."""
    router_input = decision_router.RouterInput(
        task_id=task_id,
        verdict=pipeline_result.verdict,
        confidence=confidence.composite,
        invariants_violated=[],
        defect_classes=_derive_defect_classes(orchestration.results),
        has_security_breach=_has_security_breach(orchestration.results),
    )
    try:
        route = await decision_router.route_and_log(pool, router_input)
    except Exception as exc:
        logger.warning("decision_router failed: %s", exc)
        return None, []

    promotion_trace: list[dict[str, Any]] = []
    if route.route == decision_router.Route.ROBUST_SUCCESS:
        try:
            outcomes = await promotion_engine.run_full_pipeline(
                pool, task_id, artifact_version,
            )
            promotion_trace = [o.to_dict() for o in outcomes]
        except Exception as exc:
            logger.warning("promotion_engine failed: %s", exc)
    elif route.route == decision_router.Route.CRITICAL_FAIL:
        try:
            await promotion_engine.rollback(
                pool, task_id, artifact_version,
                reason=route.rationale or "critical_fail route",
            )
        except Exception as exc:
            logger.warning("rollback failed: %s", exc)
    return route, promotion_trace


async def _run_quality_gates_v8_5(
    pool: Any,
    task_id: str,
    workspace: Workspace,
) -> dict[str, Any] | None:
    """V8.5F : execute les 6 quality gates, calcule le breakdown 100 pts,
    persiste dans delivery_quality_gates + tasks.validation_breakdown_json.

    Defensif : si tout casse, on log et on retourne None — on ne bloque pas
    le pipeline existant (decision_router continuera avec le verdict V1).
    """
    try:
        engine = QualityGatesEngine(pytest_timeout_s=120)
        async with pool.acquire() as conn:
            attempt = await conn.fetchval(
                """
                UPDATE tasks
                   SET validation_attempts = COALESCE(validation_attempts, 0) + 1
                 WHERE id = $1
             RETURNING validation_attempts
                """,
                UUID(task_id),
            )
        attempt_number = int(attempt or 1)

        gates_result = await engine.validate_deliverable(
            workspace.root, project_id=task_id,
        )
        await persist_gates_results(pool, task_id, attempt_number, gates_result)

        breakdown = compute_breakdown(gates_result)
        breakdown_dict = breakdown.to_dict()

        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE tasks
                   SET validation_breakdown_json = $2::jsonb,
                       validation_decision = $3,
                       quality_gates_history_json = COALESCE(
                           quality_gates_history_json, '[]'::jsonb
                       ) || $4::jsonb
                 WHERE id = $1
                """,
                UUID(task_id),
                json.dumps(breakdown_dict),
                breakdown.decision,
                json.dumps([{
                    "attempt": attempt_number,
                    "overall": gates_result.overall_status,
                    "summary": gates_result.summary,
                    "decision": breakdown.decision,
                    "total": breakdown.total,
                }]),
            )

        if breakdown.decision != "REJECTED":
            try:
                await QualityGatesEngine.mark_fixed(pool, task_id, attempt_number)
            except Exception as exc:
                logger.warning("mark_failures_fixed failed: %s", exc)

        logger.info(
            "v8.5F gates : decision=%s total=%d attempt=%d %s",
            breakdown.decision, breakdown.total, attempt_number,
            gates_result.summary,
        )
        return {
            "attempt_number": attempt_number,
            "decision": breakdown.decision,
            "total": breakdown.total,
            "overall_status": gates_result.overall_status,
            "breakdown": breakdown_dict,
        }
    except Exception as exc:  # noqa: BLE001 — defensif, on ne bloque pas
        logger.warning("quality_gates_v8_5 failed (non-blocking): %s", exc)
        return None


async def _maybe_reenqueue_for_regen(
    task_id: str,
    gates_summary: dict[str, Any] | None,
) -> bool:
    """V8.5F : re-enqueue auto si REJECTED et attempts < 3.

    Retourne True si une re-execution a ete enqueuee.
    """
    if not gates_summary or gates_summary.get("decision") != "REJECTED":
        return False
    attempt = int(gates_summary.get("attempt_number", 0))
    if attempt >= 3:
        logger.warning(
            "v8.5F regen : task=%s exhausted (%d attempts) — keeping REJECTED",
            task_id, attempt,
        )
        return False

    try:
        from arq.connections import RedisSettings, create_pool
        redis = await create_pool(RedisSettings(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD or None,
            database=settings.REDIS_DB,
            ssl=__import__("ssl").create_default_context() if settings.REDIS_SSL else None,
            ssl=__import__("ssl").create_default_context() if settings.REDIS_SSL else None,
        ))
        try:
            await redis.enqueue_job(
                "run_task", str(task_id),
                _queue_name="uba:run_task",
                _job_id=f"regen-{task_id}-{attempt + 1}",
            )
        finally:
            await redis.aclose()
        logger.info("v8.5F regen : re-enqueued task=%s next_attempt=%d",
                    task_id, attempt + 1)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("v8.5F regen enqueue failed: %s", exc)
        return False


# --------------------------------------------------------------------------- run_task

async def run_task(_ctx: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Pipeline V3 : DAG -> validation -> confidence -> persistence + memory.

    Etapes :
        1. Load task + DAG execution
        2. Level 0 structural validation
        3. Validation pipeline + confidence scoring
        4. Persist results (artifacts, logs, tasks status)
        5. Update learning memory + auto-optim
        6. Decision router + promotion/rollback
    """
    start = time.perf_counter()
    logger.info("run_task %s", task_id)
    pool = get_pool()
    task_uuid = UUID(task_id)

    # 1. Load + DAG
    spec, priority = await _load_task(pool, task_uuid)
    orchestration = await run_dag(task_id=task_id, spec=spec, priority=priority)
    workspace = orchestration.workspace
    manifest = workspace.manifest()

    # 2. Level 0
    await _run_level_zero(pool, workspace, manifest, task_id)

    # 3. Validation + confidence
    pipeline_result, confidence, thresholds = await _run_validation_and_confidence(
        pool, workspace, orchestration, manifest,
    )

    # 4. Persist
    await _persist_results(pool, task_uuid, orchestration,
                            pipeline_result, confidence, workspace, manifest)

    duration_ms = int((time.perf_counter() - start) * 1000)
    total_cost = await total_cost_for_task(pool, task_id)

    # 5. Learning memory + auto-optim
    await _update_learning_memory(
        pool, task_id, spec, orchestration, pipeline_result,
        confidence, len(manifest), total_cost, duration_ms,
    )
    await _run_auto_optim(pool)

    # 6. Decision router + promotion
    artifact_version = _artifact_version(manifest)
    route, promotion_trace = await _run_decision_router_and_promotion(
        pool, task_id, pipeline_result, confidence, orchestration, artifact_version,
    )

    # 7. V8.5F : 6 quality gates + breakdown 100 pts + auto-regen si REJECTED
    gates_summary = await _run_quality_gates_v8_5(pool, task_id, workspace)
    regen_enqueued = await _maybe_reenqueue_for_regen(task_id, gates_summary)

    return {
        "task_id": task_id,
        "verdict": pipeline_result.verdict,
        "score": pipeline_result.global_score,
        "confidence": confidence.to_dict(),
        "cost_usd": total_cost,
        "domain_tags": extract_domain_tags(spec),
        "waves": orchestration.waves,
        "artifacts": len(manifest),
        "thresholds_used": thresholds.to_dict(),
        "router": route.to_dict() if route else None,
        "promotion": promotion_trace,
        "quality_gates_v8_5": gates_summary,
        "regen_enqueued": regen_enqueued,
    }


def _artifact_version(manifest: list[dict[str, Any]]) -> str:
    """Version = SHA-256 concat des `sha256` de chaque fichier du manifest."""
    import hashlib
    h = hashlib.sha256()
    for m in sorted(manifest, key=lambda x: str(x.get("path", ""))):
        h.update(str(m.get("sha256", "")).encode("utf-8"))
    return h.hexdigest()


def _derive_defect_classes(results: dict[str, AgentResult]) -> list[str]:
    classes: set[str] = set()
    for agent_id, r in results.items():
        if r.status != "success":
            continue
        out = r.output or {}
        if agent_id == "agent-02-sonarqube" and out.get("severity_counts", {}).get("HIGH", 0) > 0:
            classes.add("security_fix")
        if agent_id == "agent-04-pytest" and out.get("tests_failed", 0) > 0:
            classes.add("behavior_fix")
        if agent_id == "agent-14-linter" and out.get("issues_count", 0) > 20:
            classes.add("local_fix")
        if agent_id == "agent-18-conformite-dz" and not out.get("passed", True):
            classes.add("contract_fix")
    return sorted(classes)


def _has_security_breach(results: dict[str, AgentResult]) -> bool:
    for agent_id, r in results.items():
        if agent_id != "agent-11-security":
            continue
        out = r.output or {}
        if int(out.get("secrets_count", 0)) > 0:
            return True
        findings = out.get("findings", {})
        if isinstance(findings, dict) and findings.get("secrets"):
            return True
    return False


async def startup(_ctx: dict[str, Any]) -> None:
    """Initialise le pool BDD et charge les 23 agents au demarrage du worker."""
    await init_pool()
    registry = AgentRegistry.get_instance()
    await registry.initialize_all()
    logger.info("Worker started, %d agents ready", len(registry.list_all()))


async def shutdown(_ctx: dict[str, Any]) -> None:
    """Ferme proprement le pool BDD a l'arret du worker."""
    await close_pool()


RUN_TASK_QUEUE = "uba:run_task"


class WorkerSettings:
    """Configuration Arq : fonctions exposees + lifecycle + connexion Redis."""
    functions: ClassVar[list[Any]] = [run_task]
    queue_name = RUN_TASK_QUEUE
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        database=settings.REDIS_DB,
            ssl=__import__("ssl").create_default_context() if settings.REDIS_SSL else None,
            ssl=__import__("ssl").create_default_context() if settings.REDIS_SSL else None,
    )
    max_jobs = 10
    job_timeout = 900
