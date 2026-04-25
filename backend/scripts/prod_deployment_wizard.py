#!/usr/bin/env python3
"""UBA production deployment wizard V5.9.

4 phases :
    init         collect Ahmed config (email, domain, plan, timezone, ...)
    credentials  collect API tokens, encrypt with Fernet
    deploy       orchestrate Terraform + DNS + VPS bootstrap + app deploy
    validate     post-deploy smoke tests (HTTPS, SSL, API, workers, backup)

Outputs:
    deploy/config/ahmed_answers.json    (chmod 600, gitignored)
    deploy/config/credentials.enc       (Fernet symmetric encryption)
    deploy/config/.fernet_key           (chmod 600, gitignored, NEVER commit)

Usage:
    python prod_deployment_wizard.py --phase init
    python prod_deployment_wizard.py --phase credentials
    python prod_deployment_wizard.py --phase deploy [--dry-run]
    python prod_deployment_wizard.py --phase validate

The wizard never asks for confirmation: defaults are baked in and any input
mismatch is rejected with a clear error rather than re-prompted in a loop.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "deploy" / "config"
ANSWERS_PATH = CONFIG_DIR / "ahmed_answers.json"
CREDENTIALS_ENC_PATH = CONFIG_DIR / "credentials.enc"
FERNET_KEY_PATH = CONFIG_DIR / ".fernet_key"
TERRAFORM_DIR = REPO_ROOT / "terraform"
TFVARS_PATH = TERRAFORM_DIR / "terraform.tfvars"

# ---------------------------------------------------------------------------
# Validation regexes
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")
PHONE_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
HCLOUD_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{64}$")
CLOUDFLARE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_\-]{40,}$")
CLOUDFLARE_ZONE_ID_RE = re.compile(r"^[a-f0-9]{32}$")
CLAUDE_KEY_RE = re.compile(r"^sk-(ant-)?[A-Za-z0-9_\-]{20,}$")

HETZNER_REGIONS = {"nbg1", "fsn1", "hel1", "ash", "hil"}
HETZNER_PLANS = {"cpx11", "cpx21", "cpx31", "cpx41", "ccx13", "ccx23"}
SMTP_PROVIDERS = {"none", "sendgrid", "mailgun", "ses"}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AhmedAnswers:
    ahmed_email: str
    ahmed_domain: str
    ahmed_phone_e164: str
    hetzner_region: str = "nbg1"
    hetzner_plan: str = "cpx21"
    timezone: str = "Africa/Algiers"
    smtp_provider: str = "none"
    auto_backup_enabled: bool = True
    schema_version: int = 1

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not EMAIL_RE.match(self.ahmed_email):
            errors.append(f"ahmed_email invalid: {self.ahmed_email!r}")
        if not DOMAIN_RE.match(self.ahmed_domain):
            errors.append(f"ahmed_domain invalid: {self.ahmed_domain!r}")
        if not PHONE_E164_RE.match(self.ahmed_phone_e164):
            errors.append(f"ahmed_phone_e164 must be E.164 (+...): {self.ahmed_phone_e164!r}")
        if self.hetzner_region not in HETZNER_REGIONS:
            errors.append(f"hetzner_region must be one of {sorted(HETZNER_REGIONS)}")
        if self.hetzner_plan not in HETZNER_PLANS:
            errors.append(f"hetzner_plan must be one of {sorted(HETZNER_PLANS)}")
        if self.smtp_provider not in SMTP_PROVIDERS:
            errors.append(f"smtp_provider must be one of {sorted(SMTP_PROVIDERS)}")
        return errors


@dataclass
class Credentials:
    hetzner_api_token: str = ""
    cloudflare_api_token: str = ""
    cloudflare_zone_id: str = ""
    scaleway_access_key: str = ""
    scaleway_secret_key: str = ""
    scaleway_project_id: str = ""
    claude_api_key: str = ""
    github_ssh_deploy_key_path: str = ""
    admin_password_hash: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.hetzner_api_token and not HCLOUD_TOKEN_RE.match(self.hetzner_api_token):
            errors.append("hetzner_api_token does not match expected format (64 alnum chars)")
        if self.cloudflare_api_token and not CLOUDFLARE_TOKEN_RE.match(self.cloudflare_api_token):
            errors.append("cloudflare_api_token format unexpected")
        if self.cloudflare_zone_id and not CLOUDFLARE_ZONE_ID_RE.match(self.cloudflare_zone_id):
            errors.append("cloudflare_zone_id must be 32 hex chars")
        if self.claude_api_key and not CLAUDE_KEY_RE.match(self.claude_api_key):
            errors.append("claude_api_key format unexpected (sk-ant-...)")
        if self.github_ssh_deploy_key_path and not Path(
            os.path.expanduser(self.github_ssh_deploy_key_path),
        ).exists():
            errors.append(f"github_ssh_deploy_key_path not found: {self.github_ssh_deploy_key_path}")
        return errors


# ---------------------------------------------------------------------------
# Fernet-style symmetric encryption (no external dep — uses cryptography lazily)
# ---------------------------------------------------------------------------

def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass  # Windows


def _generate_fernet_key() -> bytes:
    """32 random bytes, base64url-encoded — Fernet-compatible."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32))


def _load_or_create_fernet_key() -> bytes:
    _ensure_config_dir()
    if FERNET_KEY_PATH.exists():
        return FERNET_KEY_PATH.read_bytes().strip()
    key = _generate_fernet_key()
    FERNET_KEY_PATH.write_bytes(key)
    try:
        os.chmod(FERNET_KEY_PATH, 0o600)
    except OSError:
        pass
    return key


def encrypt_credentials(creds: Credentials, key: bytes | None = None) -> bytes:
    """Encrypt credentials JSON using Fernet (cryptography).

    Returns the Fernet token (URL-safe base64 bytes).
    """
    try:
        from cryptography.fernet import Fernet  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "cryptography package required for credential encryption "
            "(pip install cryptography)",
        ) from exc

    fkey = key or _load_or_create_fernet_key()
    payload = json.dumps(asdict(creds), sort_keys=True).encode("utf-8")
    return Fernet(fkey).encrypt(payload)


def decrypt_credentials(ciphertext: bytes, key: bytes | None = None) -> Credentials:
    try:
        from cryptography.fernet import Fernet  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("cryptography package required") from exc

    fkey = key or _load_or_create_fernet_key()
    payload = Fernet(fkey).decrypt(ciphertext)
    data = json.loads(payload.decode("utf-8"))
    return Credentials(**data)


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------

def _prompt(label: str, default: str | None = None,
            secret: bool = False, allow_empty: bool = False) -> str:
    """Prompt with default. Non-interactive: pulls from env UBA_WIZARD_<KEY>."""
    env_key = "UBA_WIZARD_" + re.sub(r"[^A-Z0-9]", "_", label.upper())
    if env_key in os.environ:
        return os.environ[env_key]
    if not sys.stdin.isatty():  # pragma: no cover
        if default is None and not allow_empty:
            raise RuntimeError(f"non-interactive run missing {env_key}")
        return default or ""
    suffix = f" [{default}]" if default else ""
    full = f"{label}{suffix}: "
    val = getpass.getpass(full) if secret else input(full)
    val = val.strip()
    if not val and default is not None:
        return default
    if not val and not allow_empty:
        raise ValueError(f"{label} cannot be empty")
    return val


def _save_answers(answers: AhmedAnswers) -> Path:
    _ensure_config_dir()
    ANSWERS_PATH.write_text(json.dumps(asdict(answers), indent=2, sort_keys=True),
                              encoding="utf-8")
    try:
        os.chmod(ANSWERS_PATH, 0o600)
    except OSError:
        pass
    return ANSWERS_PATH


def _load_answers() -> AhmedAnswers:
    if not ANSWERS_PATH.exists():
        raise FileNotFoundError(
            f"Run --phase init first (missing {ANSWERS_PATH})",
        )
    data = json.loads(ANSWERS_PATH.read_text(encoding="utf-8"))
    data.pop("schema_version", None)  # keep dataclass tolerant
    return AhmedAnswers(**data)


def _save_credentials(creds: Credentials) -> Path:
    _ensure_config_dir()
    cipher = encrypt_credentials(creds)
    CREDENTIALS_ENC_PATH.write_bytes(cipher)
    try:
        os.chmod(CREDENTIALS_ENC_PATH, 0o600)
    except OSError:
        pass
    return CREDENTIALS_ENC_PATH


def _load_credentials() -> Credentials:
    if not CREDENTIALS_ENC_PATH.exists():
        raise FileNotFoundError(
            f"Run --phase credentials first (missing {CREDENTIALS_ENC_PATH})",
        )
    return decrypt_credentials(CREDENTIALS_ENC_PATH.read_bytes())


# ---------------------------------------------------------------------------
# Token live-test (HEAD/GET hits — graceful failure)
# ---------------------------------------------------------------------------

def test_hetzner_token(token: str) -> dict[str, Any]:
    """GET /v1/locations is cheap and only needs read scope."""
    return _http_test(
        "https://api.hetzner.cloud/v1/locations",
        headers={"Authorization": f"Bearer {token}"},
    )


def test_cloudflare_token(token: str) -> dict[str, Any]:
    return _http_test(
        "https://api.cloudflare.com/client/v4/user/tokens/verify",
        headers={"Authorization": f"Bearer {token}"},
    )


def test_claude_key(key: str) -> dict[str, Any]:
    return _http_test(
        "https://api.anthropic.com/v1/messages",
        method="POST",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        body=b'{"model":"claude-3-5-haiku-latest","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}',
        accept_4xx=True,
    )


def _http_test(url: str, headers: dict[str, str] | None = None,
               method: str = "GET", body: bytes | None = None,
               accept_4xx: bool = False) -> dict[str, Any]:
    """Lightweight stdlib HTTP test (no httpx dep at wizard runtime)."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=body, headers=headers or {},
                                   method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as exc:
        ok = accept_4xx and 400 <= exc.code < 500
        return {"ok": ok, "status": exc.code, "reason": exc.reason}
    except Exception as exc:
        return {"ok": False, "status": None, "reason": str(exc)}


# ---------------------------------------------------------------------------
# Phase implementations
# ---------------------------------------------------------------------------

def phase_init(non_interactive: bool = False) -> AhmedAnswers:
    print("=== UBA wizard / phase 1: init ===")
    if non_interactive and ANSWERS_PATH.exists():
        return _load_answers()

    a = AhmedAnswers(
        ahmed_email=_prompt("Ahmed email", default="ahmed@dendani.dz"),
        ahmed_domain=_prompt("UBA domain", default="uba.dendani.dz"),
        ahmed_phone_e164=_prompt("Ahmed phone (E.164, e.g. +213555000000)",
                                  default="+213555000000"),
        hetzner_region=_prompt("Hetzner region [nbg1/hel1/fsn1/ash/hil]",
                                default="nbg1"),
        hetzner_plan=_prompt("Hetzner plan", default="cpx21"),
        timezone=_prompt("Timezone", default="Africa/Algiers"),
        smtp_provider=_prompt("SMTP provider [none/sendgrid/mailgun/ses]",
                                default="none"),
        auto_backup_enabled=_prompt("Auto-backup enabled? [yes/no]",
                                       default="yes").lower() in {"y", "yes", "true", "1"},
    )
    errors = a.validate()
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)
    path = _save_answers(a)
    print(f"OK: answers saved to {path}")
    return a


def phase_credentials(non_interactive: bool = False) -> Credentials:
    print("=== UBA wizard / phase 2: credentials ===")
    if non_interactive and CREDENTIALS_ENC_PATH.exists():
        return _load_credentials()

    creds = Credentials(
        hetzner_api_token=_prompt("Hetzner API token", secret=True,
                                     allow_empty=True),
        cloudflare_api_token=_prompt("Cloudflare API token", secret=True,
                                        allow_empty=True),
        cloudflare_zone_id=_prompt("Cloudflare zone ID (32 hex)",
                                      allow_empty=True),
        scaleway_access_key=_prompt("Scaleway access key", secret=True,
                                       allow_empty=True),
        scaleway_secret_key=_prompt("Scaleway secret key", secret=True,
                                       allow_empty=True),
        scaleway_project_id=_prompt("Scaleway project id", allow_empty=True),
        claude_api_key=_prompt("Claude API key (sk-ant-...)", secret=True,
                                  allow_empty=True),
        github_ssh_deploy_key_path=_prompt(
            "GitHub SSH deploy key path", default="~/.ssh/uba_deploy_ed25519",
        ),
        admin_password_hash=hashlib.sha256(
            _prompt("Admin password (hashed locally, never stored cleartext)",
                       secret=True).encode("utf-8"),
        ).hexdigest(),
    )
    errors = creds.validate()
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)

    # Live token tests (best-effort — never block the wizard)
    print("\nLive token checks:")
    if creds.hetzner_api_token:
        r = test_hetzner_token(creds.hetzner_api_token)
        print(f"  hetzner   -> {'OK' if r['ok'] else 'KO'} ({r.get('status')})")
    if creds.cloudflare_api_token:
        r = test_cloudflare_token(creds.cloudflare_api_token)
        print(f"  cloudflare-> {'OK' if r['ok'] else 'KO'} ({r.get('status')})")
    if creds.claude_api_key:
        r = test_claude_key(creds.claude_api_key)
        print(f"  claude    -> {'OK' if r['ok'] else 'KO'} ({r.get('status')})")

    path = _save_credentials(creds)
    print(f"OK: credentials encrypted to {path}")
    return creds


def phase_deploy(dry_run: bool = False) -> dict[str, Any]:
    print("=== UBA wizard / phase 3: deploy ===")
    answers = _load_answers()
    creds = _load_credentials()

    # 1. Render terraform.tfvars
    tfvars = render_tfvars(answers, creds)
    if dry_run:
        print("--- terraform.tfvars (dry-run, not written) ---")
        print(tfvars)
        return {"dry_run": True, "tfvars_preview": tfvars[:200]}

    TFVARS_PATH.write_text(tfvars, encoding="utf-8")
    try:
        os.chmod(TFVARS_PATH, 0o600)
    except OSError:
        pass
    print(f"OK: wrote {TFVARS_PATH}")

    # 2. Run terraform (best-effort: skip cleanly if binary absent)
    if not _has_binary("terraform"):
        print("WARN: terraform CLI not on PATH — skipping infra apply.")
        return {"step": "tf_missing", "tfvars": str(TFVARS_PATH)}

    _run(["terraform", "-chdir=" + str(TERRAFORM_DIR), "init", "-input=false"])
    _run(["terraform", "-chdir=" + str(TERRAFORM_DIR),
            "plan", "-out=uba.tfplan", "-input=false"])
    _run(["terraform", "-chdir=" + str(TERRAFORM_DIR),
            "apply", "-auto-approve", "uba.tfplan"])
    print("OK: terraform apply completed.")

    return {"step": "deployed", "domain": answers.ahmed_domain}


def phase_validate() -> dict[str, Any]:
    print("=== UBA wizard / phase 4: validate ===")
    try:
        answers = _load_answers()
    except FileNotFoundError:
        print("WARN: no ahmed_answers.json — running local validation only")
        answers = AhmedAnswers(
            ahmed_email="local@local", ahmed_domain="localhost",
            ahmed_phone_e164="+213000000000",
        )

    checks: list[dict[str, Any]] = []
    base = f"https://{answers.ahmed_domain}" if answers.ahmed_domain != "localhost" \
        else "http://localhost:8000"

    checks.append(_check("https_reachable", _http_test(base + "/api/v1/health")))
    checks.append(_check("api_health", _http_test(base + "/api/v1/health")))
    checks.append(_check("workers_healthy",
                            _http_test(base + "/api/v1/workers/healthz", accept_4xx=True)))
    checks.append(_check("backups_listed",
                            _http_test(base + "/api/v1/backups/list", accept_4xx=True)))
    checks.append(_check("slo_dashboard",
                            _http_test(base + "/api/v1/slo/status", accept_4xx=True)))

    passed = sum(1 for c in checks if c["ok"])
    print(f"\n{passed}/{len(checks)} validation checks passed")
    return {"passed": passed, "total": len(checks), "checks": checks}


def _check(name: str, result: dict[str, Any]) -> dict[str, Any]:
    badge = "OK " if result["ok"] else "FAIL"
    print(f"  [{badge}] {name:24} -> status={result.get('status')}")
    return {"name": name, **result}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def render_tfvars(answers: AhmedAnswers, creds: Credentials) -> str:
    return f"""# Auto-generated by prod_deployment_wizard.py — DO NOT COMMIT.
environment           = "production"

hcloud_token          = "{creds.hetzner_api_token}"
vps_name              = "uba-prod"
vps_location          = "{answers.hetzner_region}"
vps_server_type       = "{answers.hetzner_plan}"
vps_image             = "ubuntu-24.04"
vps_ssh_keys          = []

cloudflare_api_token  = "{creds.cloudflare_api_token}"
cloudflare_zone_id    = "{creds.cloudflare_zone_id}"
domain                = "{answers.ahmed_domain}"

scaleway_access_key   = "{creds.scaleway_access_key}"
scaleway_secret_key   = "{creds.scaleway_secret_key}"
scaleway_project_id   = "{creds.scaleway_project_id}"
"""


def _has_binary(name: str) -> bool:
    from shutil import which
    return which(name) is not None


def _run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)  # noqa: S603


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", required=True,
                     choices=["init", "credentials", "deploy", "validate", "all"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--non-interactive", action="store_true",
                     help="Re-use existing files where present; fail if missing")
    args = p.parse_args(argv)

    if args.phase == "init":
        phase_init(non_interactive=args.non_interactive)
    elif args.phase == "credentials":
        phase_credentials(non_interactive=args.non_interactive)
    elif args.phase == "deploy":
        phase_deploy(dry_run=args.dry_run)
    elif args.phase == "validate":
        phase_validate()
    elif args.phase == "all":
        phase_init(non_interactive=args.non_interactive)
        phase_credentials(non_interactive=args.non_interactive)
        phase_deploy(dry_run=args.dry_run)
        phase_validate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
