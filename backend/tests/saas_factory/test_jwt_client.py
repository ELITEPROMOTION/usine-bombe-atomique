"""Tests Phase 9M-bis — JWT client auth module."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from jose import jwt as jose_jwt

from app.security.jwt_client import (
    ISSUER,
    JWT_ALGORITHM,
    JWTClientConfigMissingError,
    JWTClientError,
    create_client_token,
    is_jwt_client_mode_enabled,
    verify_client_token,
)

VALID_SECRET = "x" * 40


@pytest.fixture
def with_secret(monkeypatch):
    monkeypatch.setenv("JWT_CLIENT_SECRET", VALID_SECRET)


class TestSecretConfig:
    def test_mode_enabled_when_set(self, with_secret):
        assert is_jwt_client_mode_enabled() is True

    def test_mode_disabled_when_unset(self, monkeypatch):
        monkeypatch.delenv("JWT_CLIENT_SECRET", raising=False)
        assert is_jwt_client_mode_enabled() is False

    def test_mode_disabled_when_too_short(self, monkeypatch):
        monkeypatch.setenv("JWT_CLIENT_SECRET", "short")
        assert is_jwt_client_mode_enabled() is False

    def test_create_raises_without_secret(self, monkeypatch):
        monkeypatch.delenv("JWT_CLIENT_SECRET", raising=False)
        with pytest.raises(JWTClientConfigMissingError):
            create_client_token(
                owner_email="x@y.com", project_id=uuid4(),
            )

    def test_create_raises_when_secret_too_short(self, monkeypatch):
        monkeypatch.setenv("JWT_CLIENT_SECRET", "shortsecret")
        with pytest.raises(JWTClientError, match="trop court"):
            create_client_token(
                owner_email="x@y.com", project_id=uuid4(),
            )


class TestCreateAndVerify:
    def test_round_trip(self, with_secret):
        pid = uuid4()
        token = create_client_token(
            owner_email="Client@Example.com", project_id=pid,
        )
        payload = verify_client_token(token)
        assert payload.sub == "client@example.com"
        assert payload.project_id == pid
        assert payload.iss == ISSUER

    def test_invalid_email(self, with_secret):
        with pytest.raises(ValueError, match="owner_email"):
            create_client_token(owner_email="notanemail", project_id=uuid4())

    def test_invalid_ttl(self, with_secret):
        with pytest.raises(ValueError, match="ttl_minutes"):
            create_client_token(
                owner_email="x@y.com", project_id=uuid4(), ttl_minutes=0,
            )

    def test_verify_empty_token(self, with_secret):
        with pytest.raises(JWTClientError, match="vide"):
            verify_client_token("")

    def test_verify_garbage(self, with_secret):
        with pytest.raises(JWTClientError, match="invalide"):
            verify_client_token("not.a.token")

    def test_verify_expired(self, with_secret):
        now = datetime.now(UTC) - timedelta(hours=2)
        claims = {
            "sub": "x@y.com",
            "project_id": str(uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=1)).timestamp()),
            "iss": ISSUER,
        }
        token = jose_jwt.encode(claims, VALID_SECRET, algorithm=JWT_ALGORITHM)
        with pytest.raises(JWTClientError):
            verify_client_token(token)

    def test_verify_wrong_issuer(self, with_secret):
        now = datetime.now(UTC)
        claims = {
            "sub": "x@y.com",
            "project_id": str(uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iss": "uba-studio/admin",
        }
        token = jose_jwt.encode(claims, VALID_SECRET, algorithm=JWT_ALGORITHM)
        with pytest.raises(JWTClientError):
            verify_client_token(token)

    def test_verify_missing_project_id(self, with_secret):
        now = datetime.now(UTC)
        claims = {
            "sub": "x@y.com",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iss": ISSUER,
        }
        token = jose_jwt.encode(claims, VALID_SECRET, algorithm=JWT_ALGORITHM)
        with pytest.raises(JWTClientError, match="incomplete"):
            verify_client_token(token)

    def test_verify_invalid_project_id_uuid(self, with_secret):
        now = datetime.now(UTC)
        claims = {
            "sub": "x@y.com",
            "project_id": "not-a-uuid",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iss": ISSUER,
        }
        token = jose_jwt.encode(claims, VALID_SECRET, algorithm=JWT_ALGORITHM)
        with pytest.raises(JWTClientError, match="project_id"):
            verify_client_token(token)
