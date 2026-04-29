"""Tests Phase 9A — Direct-Link Framework."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.saas_factory.direct_links.action_card_generator import (
    ActionCardGenerator,
    _safe_format,
)
from app.saas_factory.direct_links.catalog import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    Catalog,
    CatalogEntry,
    CatalogValidationError,
    LocaleStrings,
    load_catalog,
    load_default_catalog,
)
from app.saas_factory.direct_links.direct_link_generator import (
    DirectLinkGenerator,
    IssuedLink,
    hash_token,
)
from app.saas_factory.direct_links.validation_engine import (
    LinkResolution,
    LinkStatus,
    ValidationEngine,
    _hash_ip,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_pool() -> tuple[MagicMock, MagicMock]:
    pool = MagicMock()
    conn = MagicMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=acquire_cm)
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_cm)
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    return pool, conn


# ===========================================================================
# Catalog
# ===========================================================================
class TestCatalogLoading:
    def test_load_default_catalog_succeeds_and_has_all_required_actions(self) -> None:
        cat = load_default_catalog()
        # Les 8 actions definies dans le brief Phase 9A
        expected = {
            "kyc_validation", "card_setup", "manual_step",
            "deliverable_download", "payment_confirm",
            "domain_validation", "email_verification", "account_unlock",
        }
        assert set(cat.action_types) >= expected

    def test_each_entry_has_required_locales(self) -> None:
        cat = load_default_catalog()
        for at in cat.action_types:
            entry = cat.get(at)
            assert DEFAULT_LOCALE in entry.locales
            for loc in entry.locales:
                assert loc in SUPPORTED_LOCALES
                ls = entry.locales[loc]
                assert ls.title
                assert ls.description
                assert ls.cta_label

    def test_callback_paths_start_with_slash(self) -> None:
        cat = load_default_catalog()
        for at in cat.action_types:
            assert cat.get(at).callback_path.startswith("/")

    def test_ttl_within_bounds(self) -> None:
        cat = load_default_catalog()
        for at in cat.action_types:
            ttl = cat.get(at).default_ttl_seconds
            assert 60 <= ttl <= 30 * 24 * 3600

    def test_localize_falls_back_to_en(self) -> None:
        cat = load_default_catalog()
        entry = cat.get("kyc_validation")
        ls_unknown = entry.localize("zz")
        ls_default = entry.localize(DEFAULT_LOCALE)
        assert ls_unknown == ls_default

    def test_get_unknown_action_raises_keyerror(self) -> None:
        cat = load_default_catalog()
        with pytest.raises(KeyError):
            cat.get("does_not_exist")
        assert cat.has("kyc_validation") is True
        assert cat.has("does_not_exist") is False


class TestCatalogValidation:
    @pytest.fixture
    def temp_path(self, tmp_path: Path) -> Path:
        return tmp_path / "cat.json"

    def _base(self) -> dict:
        return {
            "version": "1.0.0",
            "actions": {
                "test_action": {
                    "default_ttl_seconds": 3600,
                    "single_use": True,
                    "requires_mandate": False,
                    "callback_path": "/test",
                    "icon": "x",
                    "locales": {
                        "en": {"title": "T", "description": "D", "cta_label": "C"},
                        "fr": {"title": "T", "description": "D", "cta_label": "C"},
                    },
                }
            },
        }

    def test_valid_minimal_catalog_loads(self, temp_path: Path) -> None:
        temp_path.write_text(json.dumps(self._base()))
        cat = load_catalog(temp_path)
        assert cat.has("test_action")

    def test_missing_en_locale_rejected(self, temp_path: Path) -> None:
        c = self._base()
        c["actions"]["test_action"]["locales"].pop("en")
        temp_path.write_text(json.dumps(c))
        with pytest.raises(CatalogValidationError):
            load_catalog(temp_path)

    def test_unsupported_locale_rejected(self, temp_path: Path) -> None:
        c = self._base()
        c["actions"]["test_action"]["locales"]["zz"] = {
            "title": "T", "description": "D", "cta_label": "C",
        }
        temp_path.write_text(json.dumps(c))
        with pytest.raises(CatalogValidationError):
            load_catalog(temp_path)

    def test_ttl_too_low_rejected(self, temp_path: Path) -> None:
        c = self._base()
        c["actions"]["test_action"]["default_ttl_seconds"] = 30
        temp_path.write_text(json.dumps(c))
        with pytest.raises(CatalogValidationError):
            load_catalog(temp_path)

    def test_ttl_too_high_rejected(self, temp_path: Path) -> None:
        c = self._base()
        c["actions"]["test_action"]["default_ttl_seconds"] = 99 * 24 * 3600
        temp_path.write_text(json.dumps(c))
        with pytest.raises(CatalogValidationError):
            load_catalog(temp_path)

    def test_bad_callback_path_rejected(self, temp_path: Path) -> None:
        c = self._base()
        c["actions"]["test_action"]["callback_path"] = "no-leading-slash"
        temp_path.write_text(json.dumps(c))
        with pytest.raises(CatalogValidationError):
            load_catalog(temp_path)

    def test_invalid_json_rejected(self, temp_path: Path) -> None:
        temp_path.write_text("{not json")
        with pytest.raises(CatalogValidationError):
            load_catalog(temp_path)


# ===========================================================================
# DirectLinkGenerator
# ===========================================================================
class TestDirectLinkGenerator:
    @pytest.fixture
    def cat(self) -> Catalog:
        return load_default_catalog()

    @pytest.mark.asyncio
    async def test_issue_returns_url_token_and_link_id(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        new_id = uuid4()
        conn.fetchrow.return_value = {"link_id": new_id}

        gen = DirectLinkGenerator(pool, cat, base_url="https://t.example/")
        link = await gen.issue(
            action_type="kyc_validation",
            target_id="hf-1",
            principal_id="user-1",
            metadata={"service": "stripe"},
        )

        assert isinstance(link, IssuedLink)
        assert link.link_id == new_id
        assert link.token  # non-vide
        assert len(link.token) >= 32
        # URL = base + callback_path + ?t=<token>
        assert link.url.startswith("https://t.example/handoff/kyc?t=")
        assert link.token in link.url
        assert link.single_use is True
        assert link.expires_at > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_issue_persists_hash_not_raw_token(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"link_id": uuid4()}
        gen = DirectLinkGenerator(pool, cat)
        link = await gen.issue(action_type="manual_step", target_id="x")

        # On verifie que le 1er argument `INSERT INTO direct_links` est bien
        # le hash et pas le token brut.
        insert_call = conn.fetchrow.await_args_list[0]
        sql = insert_call.args[0]
        assert "INSERT INTO direct_links" in sql
        token_hash_arg = insert_call.args[1]
        assert token_hash_arg == hash_token(link.token)
        assert token_hash_arg != link.token  # crucial : le hash != brut
        # Aucun argument ne contient le token brut
        for arg in insert_call.args[1:]:
            assert link.token not in str(arg)

    @pytest.mark.asyncio
    async def test_issue_each_call_yields_unique_token(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.side_effect = [{"link_id": uuid4()} for _ in range(20)]
        gen = DirectLinkGenerator(pool, cat)
        tokens = set()
        for _ in range(20):
            link = await gen.issue(action_type="manual_step", target_id="x")
            tokens.add(link.token)
        assert len(tokens) == 20  # tous uniques

    @pytest.mark.asyncio
    async def test_issue_unknown_action_type_raises(self, cat: Catalog) -> None:
        pool, _conn = _mock_pool()
        gen = DirectLinkGenerator(pool, cat)
        with pytest.raises(KeyError):
            await gen.issue(action_type="not_in_catalog", target_id="x")

    @pytest.mark.asyncio
    async def test_issue_records_audit_event(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"link_id": uuid4()}
        gen = DirectLinkGenerator(pool, cat)
        await gen.issue(action_type="manual_step", target_id="x")
        # On a appele execute() avec INSERT INTO direct_links_audit
        execute_call = conn.execute.await_args_list[0]
        sql = execute_call.args[0]
        assert "INSERT INTO direct_links_audit" in sql
        assert "'issued'" in sql

    @pytest.mark.asyncio
    async def test_issue_custom_ttl_overrides_catalog_default(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"link_id": uuid4()}
        gen = DirectLinkGenerator(pool, cat)
        link = await gen.issue(
            action_type="account_unlock",
            target_id="u1",
            ttl=timedelta(seconds=60),
        )
        # default_ttl pour account_unlock = 3600s ; l'override doit gagner.
        delta = (link.expires_at - datetime.now(UTC)).total_seconds()
        assert 50 <= delta <= 70


def test_hash_token_is_sha256_hex() -> None:
    h = hash_token("abc")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
    # Determinisme
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abcd")


# ===========================================================================
# ValidationEngine
# ===========================================================================
class TestValidationEngine:
    @pytest.fixture
    def cat(self) -> Catalog:
        return load_default_catalog()

    @pytest.mark.asyncio
    async def test_validate_valid_link_returns_valid_status(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        link_id = uuid4()
        conn.fetchrow.return_value = {
            "link_id": link_id,
            "action_type": "kyc_validation",
            "target_id": "hf-1",
            "principal_id": "u",
            "metadata_json": {"service": "stripe"},
            "single_use": True,
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
            "consumed_at": None,
            "revoked_at": None,
        }
        engine = ValidationEngine(pool, cat)
        res = await engine.validate("a-good-token-xxxxxxx", user_agent="UA", ip="1.2.3.4")
        assert res.is_valid is True
        assert res.status is LinkStatus.VALID
        assert res.link_id == link_id
        assert res.metadata == {"service": "stripe"}

    @pytest.mark.asyncio
    async def test_validate_unknown_token_audits_invalid(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None  # token inexistant
        engine = ValidationEngine(pool, cat)
        res = await engine.validate("a-bad-token-xxxxxxx")
        assert res.status is LinkStatus.UNKNOWN
        assert res.link_id is None
        # audit invalid_token enregistre
        sql = conn.execute.await_args_list[0].args[0]
        assert "INSERT INTO direct_links_audit" in sql
        assert conn.execute.await_args_list[0].args[2] == "invalid_token"

    @pytest.mark.asyncio
    async def test_validate_short_or_empty_token_returns_unknown_without_db(
        self, cat: Catalog,
    ) -> None:
        pool, conn = _mock_pool()
        engine = ValidationEngine(pool, cat)
        res1 = await engine.validate("")
        res2 = await engine.validate("short")
        assert res1.status is LinkStatus.UNKNOWN
        assert res2.status is LinkStatus.UNKNOWN
        # Aucun appel DB n'a ete fait
        conn.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_expired_returns_expired(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "link_id": uuid4(),
            "action_type": "kyc_validation",
            "target_id": "x",
            "principal_id": None,
            "metadata_json": {},
            "single_use": True,
            "expires_at": datetime.now(UTC) - timedelta(minutes=1),
            "consumed_at": None,
            "revoked_at": None,
        }
        engine = ValidationEngine(pool, cat)
        res = await engine.validate("a-token-xxxxxxxxxx")
        assert res.status is LinkStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_validate_consumed_returns_consumed(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        now = datetime.now(UTC)
        conn.fetchrow.return_value = {
            "link_id": uuid4(),
            "action_type": "kyc_validation",
            "target_id": "x",
            "principal_id": None,
            "metadata_json": {},
            "single_use": True,
            "expires_at": now + timedelta(hours=1),
            "consumed_at": now - timedelta(minutes=10),
            "revoked_at": None,
        }
        engine = ValidationEngine(pool, cat)
        res = await engine.validate("a-token-xxxxxxxxxx")
        assert res.status is LinkStatus.CONSUMED

    @pytest.mark.asyncio
    async def test_validate_revoked_returns_revoked(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        now = datetime.now(UTC)
        conn.fetchrow.return_value = {
            "link_id": uuid4(),
            "action_type": "kyc_validation",
            "target_id": "x",
            "principal_id": None,
            "metadata_json": {},
            "single_use": True,
            "expires_at": now + timedelta(hours=1),
            "consumed_at": None,
            "revoked_at": now - timedelta(minutes=1),
        }
        engine = ValidationEngine(pool, cat)
        res = await engine.validate("a-token-xxxxxxxxxx")
        assert res.status is LinkStatus.REVOKED

    @pytest.mark.asyncio
    async def test_validate_metadata_string_is_parsed(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "link_id": uuid4(),
            "action_type": "manual_step",
            "target_id": "x",
            "principal_id": None,
            "metadata_json": '{"k":"v"}',  # asyncpg peut renvoyer du str
            "single_use": False,
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
            "consumed_at": None,
            "revoked_at": None,
        }
        engine = ValidationEngine(pool, cat)
        res = await engine.validate("a-token-xxxxxxxxxx")
        assert res.metadata == {"k": "v"}

    @pytest.mark.asyncio
    async def test_consume_marks_link_consumed_when_eligible(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "link_id": uuid4(),
            "action_type": "kyc_validation",
            "target_id": "x",
            "principal_id": None,
            "metadata_json": {},
            "single_use": True,
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
        }
        engine = ValidationEngine(pool, cat)
        res = await engine.consume("a-token-xxxxxxxxxx", user_agent="UA", ip="9.9.9.9")
        assert res.status is LinkStatus.CONSUMED
        # SQL utilise l'UPDATE conditionnel
        first_sql = conn.fetchrow.await_args_list[0].args[0]
        assert "UPDATE direct_links" in first_sql
        assert "consumed_at IS NULL" in first_sql

    @pytest.mark.asyncio
    async def test_consume_already_consumed_falls_back_to_validate(
        self, cat: Catalog,
    ) -> None:
        pool, conn = _mock_pool()
        # 1er fetchrow (UPDATE) -> None (rien a consommer)
        # 2eme fetchrow (validate's SELECT) -> deja consomme
        already_consumed = {
            "link_id": uuid4(),
            "action_type": "kyc_validation",
            "target_id": "x",
            "principal_id": None,
            "metadata_json": {},
            "single_use": True,
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
            "consumed_at": datetime.now(UTC) - timedelta(minutes=1),
            "revoked_at": None,
        }
        conn.fetchrow.side_effect = [None, already_consumed]
        engine = ValidationEngine(pool, cat)
        res = await engine.consume("a-token-xxxxxxxxxx")
        assert res.status is LinkStatus.CONSUMED

    @pytest.mark.asyncio
    async def test_consume_short_token_returns_unknown_without_db(
        self, cat: Catalog,
    ) -> None:
        pool, conn = _mock_pool()
        engine = ValidationEngine(pool, cat)
        res = await engine.consume("")
        assert res.status is LinkStatus.UNKNOWN
        conn.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_revoke_returns_true_when_link_existed_and_active(
        self, cat: Catalog,
    ) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"link_id": uuid4()}
        engine = ValidationEngine(pool, cat)
        ok = await engine.revoke(uuid4(), reason="manual revocation")
        assert ok is True

    @pytest.mark.asyncio
    async def test_revoke_returns_false_when_link_unknown(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        engine = ValidationEngine(pool, cat)
        ok = await engine.revoke(uuid4(), reason="x")
        assert ok is False

    @pytest.mark.asyncio
    async def test_token_never_appears_in_audit_detail(self, cat: Catalog) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None  # token inconnu, audit invalid_token
        engine = ValidationEngine(pool, cat)
        token = "supersecret-token-abcdef-ghijkl"
        await engine.validate(token, user_agent="UA", ip="1.2.3.4")
        # Verifier qu'aucun argument du INSERT audit ne contient le token brut
        for call in conn.execute.await_args_list:
            for arg in call.args:
                assert token not in str(arg)


def test_hash_ip_consistent_and_none_for_empty() -> None:
    assert _hash_ip(None) is None
    assert _hash_ip("") is None
    h1 = _hash_ip("1.2.3.4")
    h2 = _hash_ip("1.2.3.4")
    h3 = _hash_ip("1.2.3.5")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


# ===========================================================================
# ActionCardGenerator
# ===========================================================================
class TestActionCardGenerator:
    @pytest.fixture
    def cat(self) -> Catalog:
        return load_default_catalog()

    def _link(self, cat: Catalog, action_type: str = "kyc_validation") -> IssuedLink:
        return IssuedLink(
            link_id=uuid4(),
            token="x" * 32,
            url=f"https://app.uba.studio{cat.get(action_type).callback_path}?t=tok",
            action_type=action_type,
            target_id="hf-1",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            single_use=cat.get(action_type).single_use,
        )

    def test_render_french_locale(self, cat: Catalog) -> None:
        gen = ActionCardGenerator(cat)
        card = gen.render(self._link(cat), locale="fr", context={"service": "Stripe"})
        assert card.locale == "fr"
        assert "KYC" in card.title or "Validez" in card.title
        # Substitution du placeholder {service}
        assert "Stripe" in card.description

    def test_render_unknown_locale_falls_back_to_en(self, cat: Catalog) -> None:
        gen = ActionCardGenerator(cat)
        card = gen.render(self._link(cat), locale="zz", context={"service": "Stripe"})
        assert card.locale == DEFAULT_LOCALE

    def test_render_keeps_literal_when_placeholder_missing(self, cat: Catalog) -> None:
        gen = ActionCardGenerator(cat)
        # `kyc_validation` description = "We need ... activate {service}"
        card = gen.render(self._link(cat), locale="en", context={})
        # Le placeholder est conserve plutot que de planter
        assert "{service}" in card.description

    def test_render_unknown_action_type_raises(self, cat: Catalog) -> None:
        gen = ActionCardGenerator(cat)
        bad_link = IssuedLink(
            link_id=uuid4(),
            token="x" * 32,
            url="https://x/?t=t",
            action_type="not_in_catalog",
            target_id="t",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            single_use=False,
        )
        with pytest.raises(KeyError):
            gen.render(bad_link)

    def test_render_includes_cta_url_from_link(self, cat: Catalog) -> None:
        gen = ActionCardGenerator(cat)
        link = self._link(cat, "deliverable_download")
        card = gen.render(link, locale="en", context={"project_name": "Demo"})
        assert card.cta_url == link.url
        assert "Demo" in card.description


def test_safe_format_keeps_unknown_placeholder() -> None:
    assert _safe_format("hello {name}", {"name": "Alice"}) == "hello Alice"
    assert _safe_format("hello {name}", {}) == "hello {name}"
    # Pas de plantage sur format string mal forme
    assert _safe_format("partial {", {}) == "partial {"


# ===========================================================================
# Sanity : LocaleStrings, CatalogEntry sont bien des dataclasses immuables
# ===========================================================================
class TestImmutability:
    def test_catalog_entry_is_frozen(self) -> None:
        cat = load_default_catalog()
        entry = cat.get("kyc_validation")
        with pytest.raises(Exception):  # FrozenInstanceError
            entry.icon = "different"  # type: ignore[misc]

    def test_locale_strings_is_frozen(self) -> None:
        ls = LocaleStrings(title="t", description="d", cta_label="c")
        with pytest.raises(Exception):
            ls.title = "x"  # type: ignore[misc]


def test_catalog_entry_dataclass_construction() -> None:
    e = CatalogEntry(
        action_type="x",
        default_ttl_seconds=60,
        single_use=True,
        requires_mandate=False,
        callback_path="/x",
        icon="i",
        locales={"en": LocaleStrings("t", "d", "c")},
    )
    assert e.localize("en").title == "t"
    assert e.localize("zz").title == "t"  # fallback


def test_link_resolution_is_valid_property() -> None:
    r = LinkResolution(
        status=LinkStatus.VALID,
        link_id=uuid4(),
        action_type="x",
        target_id="t",
        principal_id=None,
        metadata={},
        expires_at=datetime.now(UTC),
        single_use=False,
    )
    assert r.is_valid is True

    r2 = LinkResolution(
        status=LinkStatus.EXPIRED,
        link_id=None,
        action_type=None,
        target_id=None,
        principal_id=None,
        metadata={},
        expires_at=None,
        single_use=False,
    )
    assert r2.is_valid is False
