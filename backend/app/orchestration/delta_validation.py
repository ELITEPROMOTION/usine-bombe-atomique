"""Upgrade 26 - Delta-validation : ne rejouer que les fichiers touches
et leurs dependances directes, pas tout.

Index de hashes sur tous les fichiers ; apres un rework, on diffe,
et on ne revalide que le sous-ensemble impacte.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from app.orchestration.patch_types import required_layers_from_diff


def sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_manifest(files: dict[str, str]) -> dict[str, str]:
    return {p: sha256_of(c) for p, c in files.items()}


@dataclass
class DeltaResult:
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: int = 0

    @property
    def total_changed(self) -> int:
        return len(self.added) + len(self.modified) + len(self.removed)

    def to_dict(self) -> dict:
        return {
            "added": self.added, "modified": self.modified,
            "removed": self.removed, "unchanged": self.unchanged,
            "total_changed": self.total_changed,
        }


def diff(before: dict[str, str], after: dict[str, str]) -> DeltaResult:
    """Compare deux snapshots et retourne added/modified/removed."""
    before_hashes = hash_manifest(before)
    after_hashes = hash_manifest(after)
    added = sorted(set(after_hashes) - set(before_hashes))
    removed = sorted(set(before_hashes) - set(after_hashes))
    common = set(before_hashes) & set(after_hashes)
    modified = sorted(p for p in common if before_hashes[p] != after_hashes[p])
    unchanged = len(common) - len(modified)
    return DeltaResult(added=added, modified=modified,
                        removed=removed, unchanged=unchanged)


def layers_to_replay(delta: DeltaResult) -> list[str]:
    """Retourne la liste minimale de layers a revalider pour ce delta."""
    changed = delta.added + delta.modified + delta.removed
    return required_layers_from_diff(changed)


def estimated_time_saved_pct(delta: DeltaResult, total_files: int) -> float:
    """Estimation du gain vs full-revalidation."""
    if total_files <= 0:
        return 0.0
    ratio_changed = delta.total_changed / total_files
    return max(0.0, 1.0 - ratio_changed) * 100
