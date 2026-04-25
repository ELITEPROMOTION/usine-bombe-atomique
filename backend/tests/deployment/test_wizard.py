"""Tests prod_deployment_wizard V5.9 — no real network, no real terraform."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

import scripts.prod_deployment_wizard as wiz
from scripts.prod_deployment_wizard import (
    AhmedAnswers, Credentials, decrypt_credentials, encrypt_credentials,
    render_tfvars,
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_ahmed_answers_valid() -> None:
    a = AhmedAnswers(
        ahmed_email="ahmed@dendani.dz",
        ahmed_domain="uba.dendani.dz",
        ahmed_phone_e164="+213555000000",
    )
    assert a.validate() == []


def test_ahmed_answers_email_invalid() -> None:
    a = AhmedAnswers(
        ahmed_email="not-an-email",
        ahmed_domain="uba.dendani.dz",
        ahmed_phone_e164="+213555000000",
    )
    errs = a.validate()
    assert any("ahmed_email" in e for e in errs)


def test_ahmed_answers_domain_invalid() -> None:
    a = AhmedAnswers(
        ahmed_email="ahmed@dendani.dz",
        ahmed_domain="NotADomain!",
        ahmed_phone_e164="+213555000000",
    )
    assert any("ahmed_domain" in e for e in a.validate())


def test_ahmed_answers_phone_invalid() -> None:
    a = AhmedAnswers(
        ahmed_email="ahmed@dendani.dz",
        ahmed_domain="uba.dendani.dz",
        ahmed_phone_e164="555000000",  # missing +
    )
    assert any("ahmed_phone_e164" in e for e in a.validate())


def test_ahmed_answers_invalid_region() -> None:
    a = AhmedAnswers(
        ahmed_email="ahmed@dendani.dz",
        ahmed_domain="uba.dendani.dz",
        ahmed_phone_e164="+213555000000",
        hetzner_region="moon-base-1",
    )
    assert any("hetzner_region" in e for e in a.validate())


def test_ahmed_answers_invalid_plan() -> None:
    a = AhmedAnswers(
        ahmed_email="ahmed@dendani.dz",
        ahmed_domain="uba.dendani.dz",
        ahmed_phone_e164="+213555000000",
        hetzner_plan="cpx99",
    )
    assert any("hetzner_plan" in e for e in a.validate())


def test_ahmed_answers_smtp_provider_options() -> None:
    a = AhmedAnswers(
        ahmed_email="ahmed@dendani.dz",
        ahmed_domain="uba.dendani.dz",
        ahmed_phone_e164="+213555000000",
        smtp_provider="postfix-1990",
    )
    assert any("smtp_provider" in e for e in a.validate())


# ---------------------------------------------------------------------------
# Credentials validation
# ---------------------------------------------------------------------------

def test_credentials_empty_is_valid() -> None:
    """Allow empty fields so users can run the wizard incrementally."""
    assert Credentials().validate() == []


def test_credentials_hetzner_token_format() -> None:
    c = Credentials(hetzner_api_token="too-short")
    assert any("hetzner_api_token" in e for e in c.validate())


def test_credentials_cloudflare_zone_id_format() -> None:
    c = Credentials(cloudflare_zone_id="not-32-hex")
    assert any("cloudflare_zone_id" in e for e in c.validate())


def test_credentials_claude_key_format() -> None:
    c = Credentials(claude_api_key="not-a-key")
    assert any("claude_api_key" in e for e in c.validate())


def test_credentials_full_valid_set() -> None:
    c = Credentials(
        hetzner_api_token="A" * 64,
        cloudflare_api_token="B" * 50,
        cloudflare_zone_id="0" * 32,
        claude_api_key="sk-ant-" + "x" * 30,
    )
    assert c.validate() == []


# ---------------------------------------------------------------------------
# Encryption round-trip
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wiz, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(wiz, "FERNET_KEY_PATH", tmp_path / ".fernet_key")
    creds = Credentials(
        hetzner_api_token="A" * 64,
        cloudflare_api_token="cfb",
        admin_password_hash="abc123",
    )
    cipher = encrypt_credentials(creds)
    assert cipher != json.dumps(creds.__dict__).encode()
    restored = decrypt_credentials(cipher)
    assert restored == creds


def test_encrypt_uses_persistent_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wiz, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(wiz, "FERNET_KEY_PATH", tmp_path / ".fernet_key")
    creds = Credentials(hetzner_api_token="A" * 64)
    encrypt_credentials(creds)
    # second call: must reuse the key
    cipher2 = encrypt_credentials(creds)
    restored = decrypt_credentials(cipher2)
    assert restored == creds


# ---------------------------------------------------------------------------
# Save/load files
# ---------------------------------------------------------------------------

def test_save_and_load_answers(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wiz, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(wiz, "ANSWERS_PATH", tmp_path / "ahmed_answers.json")
    a = AhmedAnswers(
        ahmed_email="ahmed@dendani.dz",
        ahmed_domain="uba.dendani.dz",
        ahmed_phone_e164="+213555000000",
        hetzner_plan="cpx31",
    )
    wiz._save_answers(a)
    loaded = wiz._load_answers()
    assert loaded == a


def test_save_and_load_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wiz, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(wiz, "CREDENTIALS_ENC_PATH", tmp_path / "creds.enc")
    monkeypatch.setattr(wiz, "FERNET_KEY_PATH", tmp_path / ".fernet_key")
    c = Credentials(hetzner_api_token="A" * 64, claude_api_key="sk-ant-" + "z" * 30)
    wiz._save_credentials(c)
    loaded = wiz._load_credentials()
    assert loaded == c


# ---------------------------------------------------------------------------
# Tfvars rendering
# ---------------------------------------------------------------------------

def test_render_tfvars_contains_all_keys() -> None:
    a = AhmedAnswers(
        ahmed_email="ahmed@dendani.dz",
        ahmed_domain="uba.dendani.dz",
        ahmed_phone_e164="+213555000000",
        hetzner_region="hel1",
        hetzner_plan="cpx31",
    )
    c = Credentials(
        hetzner_api_token="A" * 64,
        cloudflare_api_token="cf-token",
        cloudflare_zone_id="0" * 32,
    )
    out = render_tfvars(a, c)
    assert "uba.dendani.dz" in out
    assert "hel1" in out
    assert "cpx31" in out
    assert "A" * 64 in out


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------

def test_cli_requires_phase() -> None:
    with pytest.raises(SystemExit):
        wiz.main([])


def test_cli_unknown_phase() -> None:
    with pytest.raises(SystemExit):
        wiz.main(["--phase", "moon-walk"])


def test_phase_init_via_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wiz, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(wiz, "ANSWERS_PATH", tmp_path / "answers.json")
    for key, val in {
        "UBA_WIZARD_AHMED_EMAIL": "ahmed@dendani.dz",
        "UBA_WIZARD_UBA_DOMAIN": "uba.dendani.dz",
        "UBA_WIZARD_AHMED_PHONE__E_164__E_G____213555000000_": "+213555000000",
        "UBA_WIZARD_HETZNER_REGION__NBG1_HEL1_FSN1_ASH_HIL_": "fsn1",
        "UBA_WIZARD_HETZNER_PLAN": "cpx21",
        "UBA_WIZARD_TIMEZONE": "Africa/Algiers",
        "UBA_WIZARD_SMTP_PROVIDER__NONE_SENDGRID_MAILGUN_SES_": "none",
        "UBA_WIZARD_AUTO_BACKUP_ENABLED___YES_NO_": "yes",
    }.items():
        monkeypatch.setenv(key, val)
    a = wiz.phase_init()
    assert a.hetzner_region == "fsn1"
    assert (tmp_path / "answers.json").exists()


def test_phase_deploy_dry_run(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wiz, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(wiz, "ANSWERS_PATH", tmp_path / "answers.json")
    monkeypatch.setattr(wiz, "CREDENTIALS_ENC_PATH", tmp_path / "creds.enc")
    monkeypatch.setattr(wiz, "FERNET_KEY_PATH", tmp_path / ".key")
    monkeypatch.setattr(wiz, "TFVARS_PATH", tmp_path / "out.tfvars")

    a = AhmedAnswers(ahmed_email="a@b.cd", ahmed_domain="x.y.z",
                       ahmed_phone_e164="+213555000000")
    wiz._save_answers(a)
    wiz._save_credentials(Credentials(hetzner_api_token="A" * 64))

    res = wiz.phase_deploy(dry_run=True)
    assert res["dry_run"] is True
    assert "x.y.z" in res["tfvars_preview"] or len(res["tfvars_preview"]) > 0


# ---------------------------------------------------------------------------
# Token live-test (mocked HTTP)
# ---------------------------------------------------------------------------

def test_token_check_mocked_ok() -> None:
    fake = {"ok": True, "status": 200}
    with mock.patch.object(wiz, "_http_test", return_value=fake):
        assert wiz.test_hetzner_token("A" * 64) == fake
        assert wiz.test_cloudflare_token("A" * 50) == fake


def test_token_check_mocked_failure() -> None:
    fake = {"ok": False, "status": 401, "reason": "Unauthorized"}
    with mock.patch.object(wiz, "_http_test", return_value=fake):
        assert wiz.test_claude_key("sk-ant-bad")["ok"] is False


# ---------------------------------------------------------------------------
# Phase validate (mocked HTTP)
# ---------------------------------------------------------------------------

def test_phase_validate_returns_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(wiz, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(wiz, "ANSWERS_PATH", tmp_path / "answers.json")
    a = AhmedAnswers(
        ahmed_email="a@b.cd",
        ahmed_domain="localhost",
        ahmed_phone_e164="+213555000000",
    )
    wiz._save_answers(a)
    with mock.patch.object(wiz, "_http_test",
                              return_value={"ok": True, "status": 200}):
        result = wiz.phase_validate()
    assert result["passed"] == result["total"]
    assert result["total"] == 5
