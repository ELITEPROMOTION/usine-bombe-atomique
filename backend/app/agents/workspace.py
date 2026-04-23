"""Workspace par tache : dossier isole ou chaque agent ecrit / lit des artefacts.

Les agents operent sur un dossier dedie `<root>/<task_id>` pour pouvoir
executer des outils (pytest, ruff, bandit) sur disque. La persistence BDD
reste la source de verite ; le workspace est une projection jetable.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path(tempfile.gettempdir()) / "uba_workspaces"


@dataclass
class Workspace:
    task_id: str
    root: Path
    files: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(cls, task_id: str, root: Path | None = None) -> Workspace:
        base = (root or DEFAULT_ROOT) / task_id
        if base.exists():
            shutil.rmtree(base)
        base.mkdir(parents=True, exist_ok=True)
        return cls(task_id=task_id, root=base)

    def write(self, rel_path: str, content: str) -> Path:
        target = self.root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.files[rel_path] = content
        return target

    def read(self, rel_path: str) -> str:
        return (self.root / rel_path).read_text(encoding="utf-8")

    def exists(self, rel_path: str) -> bool:
        return (self.root / rel_path).exists()

    def manifest(self) -> list[dict[str, str | int]]:
        items: list[dict[str, str | int]] = []
        for rel in sorted(self.files):
            content = self.files[rel]
            items.append({
                "path": rel,
                "size_bytes": len(content.encode("utf-8")),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "language": _language_of(rel),
                "type": _type_of(rel),
            })
        return items

    def cleanup(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)


def _language_of(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".py": "python", ".md": "markdown", ".txt": "text",
        ".toml": "toml", ".yaml": "yaml", ".yml": "yaml",
        ".json": "json", ".sh": "shell", ".sql": "sql",
    }.get(ext, "text")


def _type_of(path: str) -> str:
    name = Path(path).name.lower()
    if name.startswith("test_") or "/tests/" in path or path.startswith("tests/"):
        return "test"
    if name in {"dockerfile", "docker-compose.yml"}:
        return "docker"
    if name.endswith(".md"):
        return "documentation"
    if name in {"requirements.txt", "pyproject.toml", "pytest.ini"}:
        return "config"
    return "source_code"
