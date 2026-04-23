"""Genere rules_classification_report.md en parcourant backend/app."""
from __future__ import annotations

from pathlib import Path

from app.governance import rules_classifier


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    items = rules_classifier.scan_tree(root)
    md = rules_classifier.render_report(items)
    out = Path(__file__).resolve().parents[2] / "rules_classification_report.md"
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out}")
    print(f"\n{rules_classifier.distribution(items)}")


if __name__ == "__main__":
    main()
