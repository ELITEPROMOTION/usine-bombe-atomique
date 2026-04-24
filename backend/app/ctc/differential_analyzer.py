"""V5.3 BLOC 19 - Differential Analyzer.

Analyse fine divergences entre 2 sources Tier 1.
Categorise : version_mismatch | scope_difference | interpretation_difference | error.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any

VERSION_PATTERN = re.compile(r"\bv?(\d+(?:\.\d+)+)\b")


@dataclass
class Divergence:
    kind: str               # version_mismatch|scope_difference|interpretation_difference|error
    similarity: float       # 0..1
    resolution: str         # what to do
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _versions(text: str) -> list[str]:
    return VERSION_PATTERN.findall(text or "")


def analyze(
    text_a: str, source_a_label: str,
    text_b: str, source_b_label: str,
) -> Divergence:
    sim = _similarity(text_a, text_b)
    ver_a = _versions(text_a)
    ver_b = _versions(text_b)

    # Version mismatch
    if ver_a and ver_b and set(ver_a) != set(ver_b):
        return Divergence(
            kind="version_mismatch",
            similarity=sim,
            resolution="use_most_recent",
            details={
                "source_a": source_a_label, "versions_a": ver_a,
                "source_b": source_b_label, "versions_b": ver_b,
            },
        )

    # Scope : if one text is substantially longer, it's more specific
    len_ratio = min(len(text_a), len(text_b)) / max(len(text_a), len(text_b), 1)
    if sim > 0.5 and len_ratio < 0.6:
        larger = source_a_label if len(text_a) > len(text_b) else source_b_label
        return Divergence(
            kind="scope_difference",
            similarity=sim,
            resolution=f"prefer_more_specific:{larger}",
            details={"len_a": len(text_a), "len_b": len(text_b)},
        )

    # Interpretation difference (similarity moderate, no version)
    if 0.3 <= sim < 0.7:
        return Divergence(
            kind="interpretation_difference",
            similarity=sim,
            resolution="escalate_ahmed",
            details={"a_preview": text_a[:200], "b_preview": text_b[:200]},
        )

    # Error (too divergent)
    if sim < 0.3:
        return Divergence(
            kind="error",
            similarity=sim,
            resolution="flag_source_quality",
            details={"a_label": source_a_label, "b_label": source_b_label},
        )

    # Otherwise convergent
    return Divergence(
        kind="none",
        similarity=sim,
        resolution="convergent",
        details={},
    )
