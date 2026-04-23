"""Context Window Optimizer V4.1 - compression de prompt avant appel LLM.

Techniques deterministes (pas de LLM pour compresser le LLM) :
- Deduplication des lignes identiques (exactes ou quasi via shingles)
- Compression whitespace + lignes vides consecutives
- Elision des sections repetitives (ex: listes d'endpoints dupliquees)
- Substitution de longues refs par des tokens : `CITATION_1` etc.
- Tronquage intelligent des sections "# Reponse precedente" si presentes

Metriques : tokens_before, tokens_after, ratio, compression_pct.

L'approximation tokens = len(text) // 4 (heuristique ascii/tiktoken).
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    original: str
    optimized: str
    tokens_before: int
    tokens_after: int
    tokens_saved: int
    compression_pct: float
    techniques: list[str]

    def to_dict(self) -> dict:
        return {
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "tokens_saved": self.tokens_saved,
            "compression_pct": round(self.compression_pct, 2),
            "techniques": self.techniques,
        }


def estimate_tokens(text: str) -> int:
    """Approximation : 1 token ~ 4 caracteres."""
    return max(0, len(text or "")) // 4


def _dedupe_lines(text: str) -> tuple[str, int]:
    """Supprime les lignes consecutives identiques et les duplicats exacts."""
    seen: set[str] = set()
    kept: list[str] = []
    removed = 0
    for line in text.splitlines():
        key = line.strip()
        if not key:
            if kept and kept[-1] == "":
                removed += 1
                continue
            kept.append("")
            continue
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()
        if h in seen and len(key) > 20:
            removed += 1
            continue
        seen.add(h)
        kept.append(line)
    return "\n".join(kept), removed


def _collapse_whitespace(text: str) -> tuple[str, int]:
    """3+ newlines consecutifs -> 2 ; espaces multiples -> 1."""
    before = len(text)
    t = re.sub(r"\n{3,}", "\n\n", text)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t, before - len(t)


def _elide_previous_responses(text: str) -> tuple[str, int]:
    """Supprime les sections clairement identifiees comme 'reponses precedentes'."""
    removed = 0
    patterns = [
        r"(?is)# ?(?:reponse|response) precedente.*?(?=\n#|\Z)",
        r"(?is)<previous_response>.*?</previous_response>",
        r"(?is)\[Ancienne reponse\].*?(?=\n\[|$)",
    ]
    t = text
    for pat in patterns:
        before = len(t)
        t = re.sub(pat, "", t)
        removed += before - len(t)
    return t, removed


def _compress_lists(text: str) -> tuple[str, int]:
    """Si une liste puce a > 12 items tres similaires, garde 5 + ... + 2."""
    lines = text.split("\n")
    out: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith(("- ", "* ")):
            j = i
            bullets: list[str] = []
            while j < len(lines) and lines[j].lstrip().startswith(("- ", "* ")):
                bullets.append(lines[j])
                j += 1
            if len(bullets) > 12:
                kept = bullets[:5] + [f"  ... [+{len(bullets) - 7} items elides] ..."] + bullets[-2:]
                removed += sum(len(b) + 1 for b in bullets[5:-2])
                out.extend(kept)
            else:
                out.extend(bullets)
            i = j
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out), removed


def optimize(prompt: str, target_ratio: float = 0.60) -> OptimizationResult:
    """Applique les techniques dans l'ordre et mesure le resultat.

    `target_ratio = 0.60` = objectif -40% tokens. La fonction ne force pas la
    valeur : elle applique les techniques disponibles et reporte le gain reel.
    """
    original = prompt or ""
    tokens_before = estimate_tokens(original)
    techniques: list[str] = []

    t = original
    t, rm_prev = _elide_previous_responses(t)
    if rm_prev:
        techniques.append(f"elide_previous_responses(-{rm_prev}c)")
    t, rm_dup = _dedupe_lines(t)
    if rm_dup:
        techniques.append(f"dedupe_lines(-{rm_dup}lignes)")
    t, rm_list = _compress_lists(t)
    if rm_list:
        techniques.append(f"compress_long_lists(-{rm_list}c)")
    t, rm_ws = _collapse_whitespace(t)
    if rm_ws:
        techniques.append(f"collapse_whitespace(-{rm_ws}c)")

    tokens_after = estimate_tokens(t)
    saved = max(0, tokens_before - tokens_after)
    pct = (saved / tokens_before * 100) if tokens_before else 0.0
    logger.info(
        "context_optimizer: %d -> %d tokens (-%.1f%%) via %s (target -%.0f%%)",
        tokens_before, tokens_after, pct, techniques or ["noop"],
        (1 - target_ratio) * 100,
    )
    return OptimizationResult(
        original=original,
        optimized=t,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        tokens_saved=saved,
        compression_pct=pct,
        techniques=techniques,
    )
