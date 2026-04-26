"""V8.1 hotfix tests : audit trail INSERT-time validation.

Tests integration (DB reelle) : verifient que le trigger SQL refuse les
inserts raw avec chain_hash invalide ou prev_hash desaligne, et que TRUNCATE
est refuse. Skip si pas de DB locale.
"""
from __future__ import annotations

import hashlib
import os

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="Set RUN_DB_INTEGRATION=1 pour activer les tests DB live (skipped par defaut)",
)


@pytest.mark.asyncio
async def test_raw_insert_with_bad_chain_hash_rejected():
    import asyncpg
    pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "uba"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB", "uba"),
    )
    try:
        async with pool.acquire() as conn:
            with pytest.raises(asyncpg.RaiseError):
                await conn.execute(
                    """
                    INSERT INTO osint_audit_trail
                      (event_id, actor, module, action, target, risk_level, decision,
                       payload_hash, prev_hash, chain_hash)
                    VALUES (gen_random_uuid(), 'attacker', 'fake', 'spoof',
                            'api.dendani.dz', 'low', 'allowed',
                            encode(digest('p','sha256'),'hex'), repeat('0',64),
                            encode(digest('forged','sha256'),'hex'))
                    """,
                )
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_truncate_rejected():
    import asyncpg
    pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "uba"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB", "uba"),
    )
    try:
        async with pool.acquire() as conn:
            with pytest.raises(asyncpg.RaiseError):
                await conn.execute("TRUNCATE osint_audit_trail")
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_legitimate_append_chain_intact():
    import asyncpg
    from app.osint.legal_framework import AuditTrail
    pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "uba"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB", "uba"),
    )
    try:
        trail = AuditTrail(pool)
        for i in range(3):
            await trail.append(
                actor="v8_1_test", module="integrity_test",
                action="seq", target="api.dendani.dz",
                risk_level="low", decision="allowed",
                payload={"i": i},
            )
        rep = await trail.verify_chain()
        assert rep["integrity_ok"], rep
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_prev_hash_must_match_last_chain_hash():
    """Test que les triggers refusent un prev_hash desaligne."""
    import asyncpg
    pool = await asyncpg.create_pool(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "uba"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB", "uba"),
    )
    try:
        async with pool.acquire() as conn:
            # Tente d'inserer avec un prev_hash random au lieu du dernier chain_hash
            payload_hash = hashlib.sha256(b"x").hexdigest()
            wrong_prev = hashlib.sha256(b"wrong-prev").hexdigest()
            chain_hash = hashlib.sha256(
                (wrong_prev + payload_hash).encode()
            ).hexdigest()
            with pytest.raises(asyncpg.RaiseError):
                await conn.execute(
                    """
                    INSERT INTO osint_audit_trail
                      (event_id, actor, module, action, target, risk_level, decision,
                       payload_hash, prev_hash, chain_hash)
                    VALUES (gen_random_uuid(), 'a', 'm', 'x', 'api.dendani.dz',
                            'low', 'allowed', $1, $2, $3)
                    """,
                    payload_hash, wrong_prev, chain_hash,
                )
    finally:
        await pool.close()
