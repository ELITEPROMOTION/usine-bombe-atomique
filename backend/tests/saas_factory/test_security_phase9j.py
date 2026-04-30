"""Tests Phase 9J — JWT auth + RBAC + rate limiter + security headers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.database import get_pool
from app.routers.admin import ai as admin_ai
from app.routers.admin.dependencies import (
    AdminAuditLogger,
    AdminPrincipal,
    _strip_bearer,
    require_role,
)
from app.security.headers_middleware import (
    DEFAULT_CSP,
    DEFAULT_HSTS,
    SecurityHeadersMiddleware,
)
from app.security.jwt_admin import (
    AdminRole,
    JWTAdminError,
    JWTConfigMissingError,
    create_admin_token,
    has_permission,
    is_jwt_mode_enabled,
    require_permission,
    verify_admin_token,
)
from app.security.rate_limiter import (
    DEFAULT_MAX,
    DEFAULT_WINDOW_S,
    TokenBucketLimiter,
    _client_ip,
    _hash_scope,
    enforce_rate_limit,
)

VALID_SECRET = "x" * 40   # >= 32 chars


# ===========================================================================
# JWT admin
# ===========================================================================
class TestJWTAdmin:
    def test_create_and_verify_token(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("JWT_ADMIN_SECRET", VALID_SECRET)
        token = create_admin_token(admin_id="ahmed", role=AdminRole.ADMIN)
        payload = verify_admin_token(token)
        assert payload.sub == "ahmed"
        assert payload.role is AdminRole.ADMIN
        assert payload.exp > payload.iat

    def test_create_with_too_short_admin_id(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("JWT_ADMIN_SECRET", VALID_SECRET)
        with pytest.raises(ValueError):
            create_admin_token(admin_id="", role=AdminRole.ADMIN)

    def test_create_invalid_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_ADMIN_SECRET", VALID_SECRET)
        with pytest.raises(ValueError):
            create_admin_token(admin_id="x", role=AdminRole.ADMIN, ttl_minutes=0)
        with pytest.raises(ValueError):
            create_admin_token(admin_id="x", role=AdminRole.ADMIN, ttl_minutes=99999)

    def test_create_secret_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("JWT_ADMIN_SECRET", raising=False)
        with pytest.raises(JWTConfigMissingError):
            create_admin_token(admin_id="x", role=AdminRole.ADMIN)

    def test_create_secret_too_short(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("JWT_ADMIN_SECRET", "short")
        with pytest.raises(JWTAdminError, match="court"):
            create_admin_token(admin_id="x", role=AdminRole.ADMIN)

    def test_verify_empty_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_ADMIN_SECRET", VALID_SECRET)
        with pytest.raises(JWTAdminError, match="vide"):
            verify_admin_token("")

    def test_verify_invalid_token(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("JWT_ADMIN_SECRET", VALID_SECRET)
        with pytest.raises(JWTAdminError, match="invalide"):
            verify_admin_token("not.a.real.jwt")

    def test_verify_token_signed_with_other_secret(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("JWT_ADMIN_SECRET", VALID_SECRET)
        token = create_admin_token(admin_id="x", role=AdminRole.ADMIN)
        # Now switch the secret -> verification doit echouer
        monkeypatch.setenv("JWT_ADMIN_SECRET", "y" * 40)
        with pytest.raises(JWTAdminError):
            verify_admin_token(token)

    def test_is_jwt_mode_enabled(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("JWT_ADMIN_SECRET", raising=False)
        assert is_jwt_mode_enabled() is False
        monkeypatch.setenv("JWT_ADMIN_SECRET", "short")
        assert is_jwt_mode_enabled() is False
        monkeypatch.setenv("JWT_ADMIN_SECRET", VALID_SECRET)
        assert is_jwt_mode_enabled() is True

    def test_role_permissions(self) -> None:
        assert has_permission(AdminRole.ADMIN, "write") is True
        assert has_permission(AdminRole.VIEWER, "write") is False
        assert has_permission(AdminRole.AUDITOR, "audit") is True
        assert has_permission(AdminRole.AUDITOR, "write") is False

    def test_require_permission(self) -> None:
        require_permission(AdminRole.ADMIN, "write")  # ne leve pas
        with pytest.raises(JWTAdminError, match="permission"):
            require_permission(AdminRole.VIEWER, "write")


# ===========================================================================
# Helpers
# ===========================================================================
class TestStripBearer:
    def test_valid_bearer(self) -> None:
        assert _strip_bearer("Bearer abc123") == "abc123"

    def test_lowercase_bearer(self) -> None:
        assert _strip_bearer("bearer xyz") == "xyz"

    def test_no_authorization(self) -> None:
        assert _strip_bearer(None) is None

    def test_not_bearer(self) -> None:
        assert _strip_bearer("Basic abc") is None

    def test_bearer_without_token(self) -> None:
        assert _strip_bearer("Bearer") is None


# ===========================================================================
# Dual-mode admin auth
# ===========================================================================
def _mock_pool_for_admin() -> tuple[MagicMock, MagicMock]:
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    return pool, conn


class TestDualModeAdminAuth:
    @pytest.fixture(autouse=True)
    def _isolate_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("JWT_ADMIN_SECRET", raising=False)
        monkeypatch.delenv("UBA_ADMIN_TOKEN", raising=False)

    def _build_app(self) -> tuple[FastAPI, TestClient]:
        app = FastAPI()
        app.include_router(admin_ai.router)
        pool, conn = _mock_pool_for_admin()
        conn.fetch.return_value = []
        app.dependency_overrides[get_pool] = lambda: pool
        client = TestClient(app)
        return app, client

    def test_no_env_returns_503(self) -> None:
        app, client = self._build_app()
        r = client.get("/admin/ai/decisions")
        assert r.status_code == 503

    def test_legacy_token_only_works(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("UBA_ADMIN_TOKEN", "legacy-secret-token")
        app, client = self._build_app()
        r = client.get(
            "/admin/ai/decisions",
            headers={"X-Admin-Token": "legacy-secret-token"},
        )
        assert r.status_code == 200

    def test_legacy_wrong_token(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("UBA_ADMIN_TOKEN", "legacy-secret-token")
        app, client = self._build_app()
        r = client.get(
            "/admin/ai/decisions",
            headers={"X-Admin-Token": "wrong"},
        )
        assert r.status_code == 403

    def test_jwt_only_works(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("JWT_ADMIN_SECRET", VALID_SECRET)
        token = create_admin_token(admin_id="ahmed", role=AdminRole.ADMIN)
        app, client = self._build_app()
        r = client.get(
            "/admin/ai/decisions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    def test_jwt_invalid_returns_403(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("JWT_ADMIN_SECRET", VALID_SECRET)
        app, client = self._build_app()
        r = client.get(
            "/admin/ai/decisions",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert r.status_code == 403

    def test_bearer_ignored_when_jwt_not_configured(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Bearer envoye mais JWT pas configure : le code ignore le Bearer
        # et tombe sur le path legacy (qui exige X-Admin-Token).
        monkeypatch.setenv("UBA_ADMIN_TOKEN", "legacy-token")
        app, client = self._build_app()
        r = client.get(
            "/admin/ai/decisions",
            headers={"Authorization": "Bearer some-token"},
        )
        # 401 : "X-Admin-Token requis" — clair message
        assert r.status_code == 401
        assert "X-Admin-Token" in r.json()["detail"]

    def test_dual_mode_jwt_takes_priority(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Si les deux env sont configurees, JWT Bearer a priorite."""
        monkeypatch.setenv("JWT_ADMIN_SECRET", VALID_SECRET)
        monkeypatch.setenv("UBA_ADMIN_TOKEN", "legacy-token")
        token = create_admin_token(admin_id="ahmed", role=AdminRole.VIEWER)
        app, client = self._build_app()
        r = client.get(
            "/admin/ai/decisions",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Admin-Token": "wrong",
            },
        )
        assert r.status_code == 200   # JWT a priorite

    def test_no_credentials_at_all(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("UBA_ADMIN_TOKEN", "legacy-token")
        app, client = self._build_app()
        r = client.get("/admin/ai/decisions")
        assert r.status_code == 401


# ===========================================================================
# require_role dependency
# ===========================================================================
class TestRequireRole:
    @pytest.fixture(autouse=True)
    def _setup_jwt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_ADMIN_SECRET", VALID_SECRET)

    def test_role_check_pass(self) -> None:
        app = FastAPI()
        require_admin = require_role(AdminRole.ADMIN)

        @app.get("/admin-only")
        async def admin_only(principal=Depends(require_admin)):
            return {"who": principal.admin_id, "role": principal.role.value}

        token = create_admin_token(admin_id="ahmed", role=AdminRole.ADMIN)
        client = TestClient(app)
        r = client.get(
            "/admin-only", headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json() == {"who": "ahmed", "role": "admin"}

    def test_role_check_fail(self) -> None:
        app = FastAPI()
        require_admin = require_role(AdminRole.ADMIN)

        @app.get("/admin-only")
        async def admin_only(_principal=Depends(require_admin)):
            return {}

        token = create_admin_token(admin_id="viewer", role=AdminRole.VIEWER)
        client = TestClient(app)
        r = client.get(
            "/admin-only", headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        assert "insuffisant" in r.json()["detail"]

    def test_multiple_roles_allowed(self) -> None:
        app = FastAPI()
        admin_or_auditor = require_role(AdminRole.ADMIN, AdminRole.AUDITOR)

        @app.get("/audit-or-admin")
        async def x(_principal=Depends(admin_or_auditor)):
            return {}

        token_auditor = create_admin_token(
            admin_id="aud", role=AdminRole.AUDITOR,
        )
        client = TestClient(app)
        r = client.get(
            "/audit-or-admin",
            headers={"Authorization": f"Bearer {token_auditor}"},
        )
        assert r.status_code == 200


# ===========================================================================
# AdminAuditLogger inclut auth_mode + role
# ===========================================================================
class TestAuditLoggerWithRole:
    @pytest.mark.asyncio
    async def test_log_records_role_and_mode(self) -> None:
        pool, conn = _mock_pool_for_admin()
        new_id = uuid4()
        conn.fetchrow.return_value = {"action_id": new_id}
        logger_x = AdminAuditLogger(pool)
        principal = AdminPrincipal(
            admin_id="ahmed", token_hint="...test",
            role=AdminRole.ADMIN, auth_mode="jwt",
        )
        await logger_x.log(
            admin=principal, action_type="cancel_handoff",
            target_type="handoff", target_id="h1",
            payload={"reason": "test"},
        )
        # Le payload JSON contient _auth_mode + _role
        args = conn.fetchrow.await_args.args
        import json
        meta = json.loads(args[5])
        assert meta["_auth_mode"] == "jwt"
        assert meta["_role"] == "admin"
        assert meta["reason"] == "test"


# ===========================================================================
# Rate limiter
# ===========================================================================
class TestTokenBucketLimiter:
    def test_allows_up_to_max(self) -> None:
        clock = [1000.0]
        lim = TokenBucketLimiter(
            max_requests=3, window_seconds=60, clock=lambda: clock[0],
        )
        ok1, rem1 = lim.check("scope1")
        ok2, rem2 = lim.check("scope1")
        ok3, rem3 = lim.check("scope1")
        ok4, rem4 = lim.check("scope1")
        assert ok1 and ok2 and ok3
        assert not ok4
        assert (rem1, rem2, rem3, rem4) == (2, 1, 0, 0)

    def test_window_eviction(self) -> None:
        clock = [1000.0]
        lim = TokenBucketLimiter(
            max_requests=2, window_seconds=10, clock=lambda: clock[0],
        )
        lim.check("s")
        lim.check("s")
        ok, _ = lim.check("s")
        assert not ok
        # Avancer au-dela de la fenetre
        clock[0] = 1100.0
        ok, _ = lim.check("s")
        assert ok

    def test_isolated_scopes(self) -> None:
        lim = TokenBucketLimiter(max_requests=1)
        ok1, _ = lim.check("a")
        ok2, _ = lim.check("b")
        assert ok1 and ok2

    def test_invalid_max(self) -> None:
        with pytest.raises(ValueError):
            TokenBucketLimiter(max_requests=0)

    def test_invalid_window(self) -> None:
        with pytest.raises(ValueError):
            TokenBucketLimiter(window_seconds=0)

    def test_stats(self) -> None:
        lim = TokenBucketLimiter(max_requests=5)
        lim.check("a")
        lim.check("a")
        lim.check("b")
        stats = lim.stats
        assert stats["a"] == 2
        assert stats["b"] == 1

    def test_reset_specific_scope(self) -> None:
        lim = TokenBucketLimiter(max_requests=1)
        lim.check("a")
        lim.reset("a")
        ok, _ = lim.check("a")
        assert ok

    def test_reset_all(self) -> None:
        lim = TokenBucketLimiter(max_requests=1)
        lim.check("a")
        lim.check("b")
        lim.reset()
        assert lim.stats == {}

    def test_lru_eviction(self) -> None:
        from app.security.rate_limiter import MAX_BUCKETS
        lim = TokenBucketLimiter(max_requests=1)
        for i in range(MAX_BUCKETS + 5):
            lim.check(f"s{i}")
        assert len(lim.stats) == MAX_BUCKETS

    def test_hash_scope_deterministic(self) -> None:
        a = _hash_scope("1.2.3.4")
        b = _hash_scope("1.2.3.4")
        assert a == b
        assert len(a) == 16


class TestEnforceRateLimitDependency:
    def test_blocks_after_max(self) -> None:
        app = FastAPI()
        rate_dep = enforce_rate_limit(max_requests=3, window_seconds=60)

        @app.get("/limited")
        async def x(_=Depends(rate_dep)) -> dict:
            return {"ok": True}

        client = TestClient(app)
        for _ in range(3):
            assert client.get("/limited").status_code == 200
        # 4eme request -> 429
        r = client.get("/limited")
        assert r.status_code == 429
        assert r.headers.get("Retry-After") == "60"

    def test_client_ip_x_forwarded_for(self) -> None:
        from starlette.requests import Request

        scope = {
            "type": "http", "headers": [
                (b"x-forwarded-for", b"203.0.113.1, 10.0.0.1"),
            ],
            "client": ("127.0.0.1", 12345),
        }
        request = Request(scope)
        assert _client_ip(request) == "203.0.113.1"

    def test_client_ip_no_xff_fallback(self) -> None:
        from starlette.requests import Request

        request = Request({
            "type": "http", "headers": [],
            "client": ("203.0.113.5", 12345),
        })
        assert _client_ip(request) == "203.0.113.5"

    def test_client_ip_no_client(self) -> None:
        from starlette.requests import Request

        request = Request({
            "type": "http", "headers": [], "client": None,
        })
        assert _client_ip(request) == "unknown"

    def test_defaults(self) -> None:
        assert DEFAULT_MAX > 0
        assert DEFAULT_WINDOW_S > 0


# ===========================================================================
# Security headers middleware
# ===========================================================================
class TestSecurityHeadersMiddleware:
    def test_adds_all_headers(self) -> None:
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/x")
        async def handler() -> dict:
            return {}

        client = TestClient(app)
        r = client.get("/x")
        assert r.status_code == 200
        h = r.headers
        assert "Strict-Transport-Security" in h
        assert "Content-Security-Policy" in h
        assert h["X-Frame-Options"] == "DENY"
        assert h["X-Content-Type-Options"] == "nosniff"
        assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in h

    def test_skip_paths_no_csp(self) -> None:
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        client = TestClient(app)
        r = client.get("/openapi.json")
        # /openapi.json est dans skip_paths -> pas de CSP/HSTS, mais les
        # autres headers sont presents
        assert r.status_code == 200
        h = r.headers
        assert "Content-Security-Policy" not in h
        assert "Strict-Transport-Security" not in h
        assert h["X-Frame-Options"] == "DENY"

    def test_csp_includes_stripe(self) -> None:
        # CSP par defaut autorise les connexions a Stripe, Anthropic, Perplexity
        assert "api.stripe.com" in DEFAULT_CSP
        assert "api.anthropic.com" in DEFAULT_CSP

    def test_hsts_default_one_year(self) -> None:
        assert "max-age=31536000" in DEFAULT_HSTS

    def test_custom_skip_paths(self) -> None:
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, skip_paths=("/api",))

        @app.get("/api/x")
        async def x() -> dict:
            return {}

        client = TestClient(app)
        r = client.get("/api/x")
        assert "Content-Security-Policy" not in r.headers


# ===========================================================================
# Smoke : migration 042 SQL syntax
# ===========================================================================
def test_migration_042_file_exists() -> None:
    import pathlib

    p = pathlib.Path(
        __file__,
    ).parent.parent.parent / "migrations" / "versions" / "042_audit_trail_immutable.sql"
    assert p.exists()
    content = p.read_text(encoding="utf-8")
    # Verifie que les triggers attendus sont definis
    assert "trg_admin_actions_no_update" in content
    assert "trg_ai_decisions_log_no_update" in content
    assert "trg_hostinger_audit_no_update" in content
    assert "trg_direct_links_audit_no_update" in content
    assert "trg_webhook_events_protect" in content
    assert "trg_mandates_protect" in content
    assert "fn_block_mutations" in content
    assert "v_audit_immutability_status" in content
