"""V8 OSINT self-audit template injector.

Lors de la phase de delivery_package, lit les templates Jinja2 sous
`backend/templates/deliverable/osint_self_audit/` et les injecte dans le
livrable cible avec contexte (domaine, stack keywords, log_dir).

Toujours injecte (pas de flag) : tous les livrables UBA contiennent les 7
modules + 4 docs legaux pour conformite par defaut.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from string import Template
from typing import Any

logger = logging.getLogger("uba.orchestration.osint_inject")

TEMPLATE_DIR = Path(os.getenv("OSINT_TEMPLATE_DIR",
                               "/app/templates/deliverable/osint_self_audit"))

# Template_name -> deliverable path
TEMPLATE_MAPPING: dict[str, str] = {
    "app_self_breach_check.py.j2":          "osint/app_self_breach_check.py",
    "app_dependency_continuous_scan.yml.j2": ".github/workflows/dependency_continuous_scan.yml",
    "app_ssl_self_monitor.py.j2":           "osint/app_ssl_self_monitor.py",
    "app_subdomain_drift_detect.py.j2":     "osint/app_subdomain_drift_detect.py",
    "app_security_headers_audit.py.j2":     "osint/app_security_headers_audit.py",
    "app_log_pii_detector.py.j2":           "osint/app_log_pii_detector.py",
    "app_threat_intel_consumer.py.j2":      "osint/app_threat_intel_consumer.py",
    "LEGAL_NOTICE.md.j2":                   "LEGAL_NOTICE.md",
    "CONSENT_TEMPLATE.md.j2":               "CONSENT_TEMPLATE.md",
    "AUDIT_TRAIL_README.md.j2":             "AUDIT_TRAIL_README.md",
    "OSINT_QUICK_START.md.j2":              "OSINT_QUICK_START.md",
}


def _render_minimal(template_text: str, ctx: dict[str, Any]) -> str:
    """Implementation Jinja2-lite : remplace `{{ var | default('x') }}`.

    Pour eviter d'ajouter Jinja2 comme dep dure quand absent, on supporte un
    sous-ensemble suffisant pour ces templates.
    """
    import re

    def repl(m: "re.Match[str]") -> str:
        key = m.group(1).strip()
        # default fallback
        default = None
        if "|" in key:
            key, _, rest = key.partition("|")
            key = key.strip()
            mdef = re.match(r"\s*default\(['\"]?([^)'\"]*)['\"]?\)", rest)
            if mdef:
                default = mdef.group(1)
        val = ctx.get(key, default if default is not None else f"<{key}>")
        return str(val)

    return re.sub(r"{{\s*([^}]+)\s*}}", repl, template_text)


def build_context(*, project_name: str, own_domain: str | None = None,
                  own_email_domain: str | None = None,
                  stack_keywords: str = "python,fastapi,postgres,redis,nginx",
                  log_dir: str = "/var/log/app",
                  self_health_url: str = "http://localhost:8000/health") -> dict[str, Any]:
    return {
        "project_name": project_name,
        "own_domain": own_domain or f"{project_name}.localhost",
        "own_email_domain": own_email_domain or "example.com",
        "stack_keywords": stack_keywords,
        "log_dir": log_dir,
        "self_health_url": self_health_url,
    }


def render_all(ctx: dict[str, Any]) -> dict[str, str]:
    """Returns {target_path_in_deliverable: rendered_content}."""
    out: dict[str, str] = {}
    if not TEMPLATE_DIR.exists():
        logger.warning("template dir missing: %s", TEMPLATE_DIR)
        return out
    for template_name, target in TEMPLATE_MAPPING.items():
        src = TEMPLATE_DIR / template_name
        if not src.exists():
            logger.warning("missing template: %s", src)
            continue
        text = src.read_text(encoding="utf-8")
        out[target] = _render_minimal(text, ctx)
    return out


def inject_into_artifacts(artifacts: list[dict[str, Any]],
                           ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Mutates `artifacts` to include OSINT self-audit files.

    `artifacts` is a list of {"path": str, "content": str} dicts. Existing
    paths are preserved ; conflicting templates are skipped (delivered code wins).
    """
    rendered = render_all(ctx)
    existing_paths = {a["path"] for a in artifacts}
    added = 0
    for path, content in rendered.items():
        if path in existing_paths:
            continue
        artifacts.append({"path": path, "content": content,
                           "type": "osint_self_audit"})
        added += 1
    logger.info("osint_template_injector added=%d", added)
    return artifacts


__all__ = ["TEMPLATE_MAPPING", "build_context", "render_all",
           "inject_into_artifacts"]
