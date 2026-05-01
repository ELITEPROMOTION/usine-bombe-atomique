"""Detecteur de boucles d'appels IA inefficaces.

Hashe (prompt, response_text) pour chaque (project_id, provider) ; si la
meme paire revient `threshold` fois dans une fenetre `window_seconds`, on
leve `LoopDetectedError` — l'orchestrateur upstream peut alors degrader
ou faire un handoff.

Implementation : in-memory LRU par projet. Pas persiste : chaque process
worker garde son propre etat. C'est suffisant pour le cas typique d'une
boucle dans une seule pipeline run.
"""
from __future__ import annotations

import collections
import hashlib
import time
from dataclasses import dataclass
from typing import Final

DEFAULT_WINDOW_S: Final[int] = 300        # 5 minutes
DEFAULT_THRESHOLD: Final[int] = 3
MAX_PROJECTS_TRACKED: Final[int] = 256
MAX_HISTORY_PER_PROJECT: Final[int] = 50


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class LoopDetectedError(RuntimeError):
    def __init__(self, project_id: str, count: int) -> None:
        super().__init__(
            f"loop detected on project={project_id}: same (prompt, response) "
            f"repeated {count} times in window"
        )
        self.project_id = project_id
        self.count = count


@dataclass(frozen=True)
class _Entry:
    pair_hash: str
    timestamp: float


class LoopDetector:
    """Detecteur de boucles. Thread-safe non garanti — usage par run worker."""

    def __init__(
        self,
        *,
        threshold: int = DEFAULT_THRESHOLD,
        window_seconds: int = DEFAULT_WINDOW_S,
        clock: object = time.monotonic,
    ) -> None:
        if threshold < 2:
            raise ValueError("threshold >= 2 requis")
        self._threshold = threshold
        self._window = window_seconds
        self._clock = clock
        # OrderedDict pour LRU des projets ; deque par projet pour fenetre rolling.
        self._projects: collections.OrderedDict[str, collections.deque[_Entry]] = (
            collections.OrderedDict()
        )

    def _now(self) -> float:
        return float(self._clock())  # type: ignore[operator]

    def _evict_old(self, history: collections.deque[_Entry]) -> None:
        cutoff = self._now() - self._window
        while history and history[0].timestamp < cutoff:
            history.popleft()

    def _track_project(self, project_id: str) -> collections.deque[_Entry]:
        if project_id in self._projects:
            self._projects.move_to_end(project_id)
            return self._projects[project_id]
        # eviction LRU
        if len(self._projects) >= MAX_PROJECTS_TRACKED:
            self._projects.popitem(last=False)
        history: collections.deque[_Entry] = collections.deque(
            maxlen=MAX_HISTORY_PER_PROJECT
        )
        self._projects[project_id] = history
        return history

    def record(
        self,
        *,
        project_id: str,
        prompt: str,
        response_text: str,
    ) -> None:
        """Enregistre (prompt, response). Leve `LoopDetectedError` si boucle."""
        pair_hash = _digest(prompt + "|" + response_text)
        history = self._track_project(project_id)
        history.append(_Entry(pair_hash=pair_hash, timestamp=self._now()))
        self._evict_old(history)
        count = sum(1 for e in history if e.pair_hash == pair_hash)
        if count >= self._threshold:
            raise LoopDetectedError(project_id, count)

    def stats(self) -> dict[str, int]:
        return {pid: len(h) for pid, h in self._projects.items()}

    def reset(self, project_id: str | None = None) -> None:
        if project_id is None:
            self._projects.clear()
        else:
            self._projects.pop(project_id, None)
