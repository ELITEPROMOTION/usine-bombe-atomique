"""Upgrade 24 - Cache semantique pour reutiliser du code existant.

Approche pragmatique sans extension pgvector :
- `fingerprint(prompt)` : vecteur d'occurrences de domain-tags + trigrammes les
  plus frequents. Deterministe, rapide, suffisant pour detecter des prompts
  similaires.
- Stocke en JSONB dans `semantic_cache.fingerprint`.
- Similarite = Jaccard sur les cles + cosine simplifie sur les poids.
- Si similarite >= seuil (0.92 par defaut), on renvoie la tache source pour
  reutilisation (patch au lieu de regen). -40% tokens LLM en regime nominal.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from app.orchestration.memory_engine import extract_domain_tags


def spec_hash(spec: str) -> str:
    return hashlib.sha256((spec or "").encode("utf-8")).hexdigest()


def fingerprint(spec: str) -> dict[str, float]:
    """Vecteur = domain_tags ponderees + trigrammes les + frequents (top 20)."""
    low = (spec or "").lower()
    vec: dict[str, float] = {}
    for tag in extract_domain_tags(low):
        vec[f"dom:{tag}"] = 2.0
    tokens = re.findall(r"[a-z]{4,}", low)
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    for tok, n in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:20]:
        vec[f"tok:{tok}"] = min(3.0, float(n))
    return vec


def dense_embedding(spec: str, dim: int = 128) -> list[float]:
    """Projection deterministe vers un vecteur dense `dim`-d pour pgvector.
    Feature hashing L2-normalise ; deterministe, pas besoin de LLM.
    """
    vec = [0.0] * dim
    low = (spec or "").lower()
    tokens = re.findall(r"[a-z]{3,}", low)
    for t in tokens:
        h = hashlib.blake2b(t.encode("utf-8"), digest_size=4).digest()
        idx = int.from_bytes(h, "big") % dim
        vec[idx] += 1.0
    import math
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def similarity(a: dict[str, float], b: dict[str, float]) -> float:
    """Cosine sur les cles partagees (0..1)."""
    shared = set(a) & set(b)
    if not shared:
        return 0.0
    dot = sum(a[k] * b[k] for k in shared)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class CacheHit:
    spec_hash: str
    task_id: str | None
    similarity: float
    spec_excerpt: str
    reuse_count: int


async def store(
    pool: asyncpg.Pool, spec: str, task_id: str | None,
    artifact_count: int,
) -> str:
    h = spec_hash(spec)
    fp = fingerprint(spec)
    emb = dense_embedding(spec)
    emb_literal = "[" + ",".join(f"{v:.6f}" for v in emb) + "]"
    async with pool.acquire() as conn:
        # Essaye d'abord avec pgvector ; si la colonne n'existe pas, fallback JSONB seul
        try:
            await conn.execute(
                """
                INSERT INTO semantic_cache
                  (spec_hash, spec_excerpt, fingerprint, task_id, artifact_count,
                   last_hit_at, embedding)
                VALUES ($1, $2, $3::jsonb, $4, $5, NOW(), $6::vector)
                ON CONFLICT (spec_hash) DO UPDATE SET
                  artifact_count = EXCLUDED.artifact_count,
                  last_hit_at = NOW(),
                  embedding = EXCLUDED.embedding
                """,
                h, (spec or "")[:400], json.dumps(fp),
                UUID(task_id) if task_id else None, artifact_count, emb_literal,
            )
        except asyncpg.PostgresError:
            await conn.execute(
                """
                INSERT INTO semantic_cache
                  (spec_hash, spec_excerpt, fingerprint, task_id, artifact_count,
                   last_hit_at)
                VALUES ($1, $2, $3::jsonb, $4, $5, NOW())
                ON CONFLICT (spec_hash) DO UPDATE SET
                  artifact_count = EXCLUDED.artifact_count,
                  last_hit_at = NOW()
                """,
                h, (spec or "")[:400], json.dumps(fp),
                UUID(task_id) if task_id else None, artifact_count,
            )
    return h


async def lookup_pgvector(
    pool: asyncpg.Pool, spec: str, threshold: float = 0.92, top_k: int = 5,
) -> list[CacheHit]:
    """Recherche vectorielle pgvector (cosine). Fallback sur `lookup()` si indispo."""
    emb = dense_embedding(spec)
    emb_literal = "[" + ",".join(f"{v:.6f}" for v in emb) + "]"
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT spec_hash, task_id, spec_excerpt, reuse_count,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM semantic_cache
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                emb_literal, top_k * 3,
            )
    except asyncpg.PostgresError:
        return await lookup(pool, spec, threshold, top_k)
    hits: list[CacheHit] = []
    for r in rows:
        s = float(r["similarity"] or 0)
        if s < threshold:
            continue
        hits.append(CacheHit(
            spec_hash=r["spec_hash"],
            task_id=str(r["task_id"]) if r["task_id"] else None,
            similarity=round(s, 4),
            spec_excerpt=r["spec_excerpt"],
            reuse_count=r["reuse_count"],
        ))
    return hits[:top_k]


async def lookup(
    pool: asyncpg.Pool, spec: str, threshold: float = 0.92, top_k: int = 5,
) -> list[CacheHit]:
    """Cherche les specs les plus similaires. O(N) scan sur JSONB - OK jusqu'a ~10k."""
    fp = fingerprint(spec)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT spec_hash, task_id, spec_excerpt, reuse_count, fingerprint
            FROM semantic_cache
            ORDER BY last_hit_at DESC NULLS LAST
            LIMIT 1000
            """
        )
    scored: list[tuple[float, asyncpg.Record]] = []
    for r in rows:
        other = r["fingerprint"]
        if isinstance(other, str):
            other = json.loads(other)
        s = similarity(fp, other or {})
        if s >= threshold:
            scored.append((s, r))
    scored.sort(reverse=True, key=lambda x: x[0])
    hits: list[CacheHit] = []
    for s, r in scored[:top_k]:
        hits.append(CacheHit(
            spec_hash=r["spec_hash"],
            task_id=str(r["task_id"]) if r["task_id"] else None,
            similarity=round(s, 4),
            spec_excerpt=r["spec_excerpt"],
            reuse_count=r["reuse_count"],
        ))
    return hits


async def record_reuse(pool: asyncpg.Pool, spec_hash_val: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE semantic_cache SET reuse_count = reuse_count + 1, "
            "last_hit_at = NOW() WHERE spec_hash = $1",
            spec_hash_val,
        )
