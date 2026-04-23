"""V5.4 AJOUT CLAUDE 4 - Reasoning Fingerprint.

SHA-256 deterministe sur problem_statement normalise + technique_path.
Detecte duplicatas semantiques simples.
"""
from __future__ import annotations

import hashlib
import re


def normalize(text: str) -> str:
    if not text:
        return ""
    t = text.lower()
    t = re.sub(r"\s+", " ", t).strip()
    # Remove ponctuation non essentielle
    t = re.sub(r"[\.\!\?\,\;\:]+", "", t)
    return t


def fingerprint(
    problem_statement: str,
    technique_path: list[str] | None = None,
    rules_version: str = "v5.4",
) -> str:
    norm = normalize(problem_statement)
    path_str = ",".join(technique_path or [])
    key = f"{norm}|{path_str}|{rules_version}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def are_semantically_close(fp1: str, fp2: str) -> bool:
    """V1 : egalite stricte. A etendre avec embeddings dans V2."""
    return fp1 == fp2
