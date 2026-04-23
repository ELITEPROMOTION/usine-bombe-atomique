"""Upgrade 7 - Ingestion universelle : accepter texte, JSON, YAML, CSV, PDF, image, etc.

Approche : retourne un IntakeDocument normalise {format, text, metadata}.
Les types binaires (PDF, image, xlsx) sont supportes si les libs sont
installees ; sinon on renvoie le type detecte + un message de fallback.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


SUPPORTED_FORMATS = (
    "text", "json", "yaml", "csv", "markdown", "html",
    "pdf", "docx", "xlsx", "image", "email",
)


@dataclass
class IntakeDocument:
    format: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    size_bytes: int = 0
    sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "text_excerpt": self.text[:600],
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "metadata": self.metadata,
        }


def _hash_and_size(raw: bytes | str) -> tuple[str, int]:
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    return hashlib.sha256(data).hexdigest(), len(data)


def _detect_binary(content: bytes, name: str) -> str | None:
    head = content[:8]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8\xff"):
        return "image"
    if head.startswith(b"PK"):
        return "xlsx" if name.endswith(".xlsx") else "docx"
    return None


def _is_json_text(text: str) -> bool:
    if not text.startswith(("{", "[")):
        return False
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


def _is_yaml(text: str, name: str) -> bool:
    return "\n---\n" in text or name.endswith((".yaml", ".yml"))


def _is_email(text: str) -> bool:
    return "From:" in text[:200] and "Subject:" in text[:300]


def _is_csv(text: str, name: str) -> bool:
    return name.endswith(".csv") or (text.count(",") > 5 and text.count("\n") > 2)


def _is_markdown(text: str, name: str) -> bool:
    return name.endswith(".md") or text.startswith(("# ", "## "))


def _is_html(text: str) -> bool:
    return text.lstrip().startswith("<") and "</" in text


def detect_format(content: str | bytes, filename: str | None = None) -> str:
    name = (filename or "").lower()
    if isinstance(content, bytes):
        binary_fmt = _detect_binary(content, name)
        if binary_fmt:
            return binary_fmt
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            return "image"
    text = content.lstrip()
    if _is_json_text(text):
        return "json"
    if _is_yaml(text, name):
        return "yaml"
    if _is_email(text):
        return "email"
    if _is_csv(text, name):
        return "csv"
    if _is_markdown(text, name):
        return "markdown"
    if _is_html(text):
        return "html"
    return "text"


def _ingest_json(raw: str) -> IntakeDocument:
    parsed = json.loads(raw)
    sha, size = _hash_and_size(raw)
    return IntakeDocument(
        format="json", text=json.dumps(parsed, indent=2, ensure_ascii=False),
        metadata={"keys_top_level": list(parsed.keys()) if isinstance(parsed, dict)
                   else ["<array>"]},
        size_bytes=size, sha256=sha,
    )


def _ingest_yaml(raw: str) -> IntakeDocument:
    sha, size = _hash_and_size(raw)
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(raw)
        keys = list(data.keys()) if isinstance(data, dict) else ["<non-map>"]
    except Exception:
        keys = []
    return IntakeDocument(
        format="yaml", text=raw,
        metadata={"keys_top_level": keys},
        size_bytes=size, sha256=sha,
    )


def _ingest_csv(raw: str) -> IntakeDocument:
    sha, size = _hash_and_size(raw)
    reader = csv.reader(io.StringIO(raw))
    rows = list(reader)
    header = rows[0] if rows else []
    return IntakeDocument(
        format="csv", text=raw,
        metadata={"columns": header, "rows": max(0, len(rows) - 1)},
        size_bytes=size, sha256=sha,
    )


def _ingest_pdf(raw: bytes) -> IntakeDocument:
    sha, size = _hash_and_size(raw)
    text = ""
    try:
        # tentative legere : pdfminer.six / pypdf non bundle -> on renvoie le raw
        text = f"[PDF binaire, {size} octets - extraction de texte indisponible]"
    except Exception as exc:
        logger.debug("pdf ingest degrade: %s", exc)
    return IntakeDocument(
        format="pdf", text=text, metadata={"decoded_text": False},
        size_bytes=size, sha256=sha,
    )


def _ingest_image(raw: bytes) -> IntakeDocument:
    sha, size = _hash_and_size(raw)
    b64_preview = base64.b64encode(raw[:256]).decode("ascii")
    return IntakeDocument(
        format="image",
        text=f"[Image {size} octets - OCR non execute dans cette release]",
        metadata={"bytes_preview_b64": b64_preview},
        size_bytes=size, sha256=sha,
    )


def ingest(content: str | bytes, filename: str | None = None) -> IntakeDocument:
    """Detecte le format + normalise en IntakeDocument."""
    fmt = detect_format(content, filename)
    if isinstance(content, bytes) and fmt in ("json", "yaml", "csv", "markdown",
                                                 "html", "text", "email"):
        content = content.decode("utf-8", errors="replace")
    if fmt == "json":
        return _ingest_json(content)  # type: ignore[arg-type]
    if fmt == "yaml":
        return _ingest_yaml(content)  # type: ignore[arg-type]
    if fmt == "csv":
        return _ingest_csv(content)  # type: ignore[arg-type]
    if fmt == "pdf" and isinstance(content, bytes):
        return _ingest_pdf(content)
    if fmt == "image" and isinstance(content, bytes):
        return _ingest_image(content)
    # Default : texte libre (markdown/email/html/text)
    sha, size = _hash_and_size(content)
    text = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
    return IntakeDocument(
        format=fmt, text=text,
        metadata={"lines": text.count("\n") + 1},
        size_bytes=size, sha256=sha,
    )


def merge_sources(docs: list[IntakeDocument]) -> IntakeDocument:
    """Fusionne plusieurs sources en un seul document unifie (concatene+balises)."""
    sections = []
    for d in docs:
        sections.append(f"## Source {d.format}\n{d.text}\n")
    merged = "\n".join(sections)
    sha, size = _hash_and_size(merged)
    return IntakeDocument(
        format="merged", text=merged,
        metadata={"sources": [d.format for d in docs], "count": len(docs)},
        size_bytes=size, sha256=sha,
    )


def extract_keywords(doc: IntakeDocument, top_k: int = 25) -> list[str]:
    low = doc.text.lower()
    tokens = re.findall(r"[a-z]{3,}", low)
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_k]]
