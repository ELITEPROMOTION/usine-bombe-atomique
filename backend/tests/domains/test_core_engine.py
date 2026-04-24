"""Tests core : BaseDomain + DomainRegistry + DomainRouter + CELEvaluator + RulesEngine."""
from __future__ import annotations

import pytest

from app.core import DomainContext, DomainRegistry, DomainRouter
from app.core.domain_results import Issue, ValidationResult
from app.core.rules_engine import CELEvaluator, Rule, RulesEngine

pytestmark = pytest.mark.asyncio


# ============================================================================
# DomainContext - 8 tests
# ============================================================================

def test_ctx_basic() -> None:
    ctx = DomainContext(tenant_id="t1", user_id="u1", domain_id="x")
    assert ctx.tenant_id == "t1"
    assert ctx.correlation_id  # auto-generated
    assert ctx.locale == "fr-DZ"
    assert ctx.timezone_name == "Africa/Algiers"


def test_ctx_frozen() -> None:
    ctx = DomainContext(tenant_id="t", user_id="u", domain_id="x")
    with pytest.raises(Exception):
        ctx.tenant_id = "other"  # type: ignore[misc]


def test_ctx_permissions_exact() -> None:
    ctx = DomainContext(
        tenant_id="t", user_id="u", domain_id="x",
        permissions=frozenset(["x:read", "x:write"]),
    )
    assert ctx.has_permission("x:read")
    assert ctx.has_permission("x:write")
    assert not ctx.has_permission("x:delete")


def test_ctx_permissions_wildcard() -> None:
    ctx = DomainContext(
        tenant_id="t", user_id="u", domain_id="x",
        permissions=frozenset(["x:*"]),
    )
    assert ctx.has_permission("x:read")
    assert ctx.has_permission("x:anything")
    assert not ctx.has_permission("y:read")


def test_ctx_feature_flags_default_false() -> None:
    ctx = DomainContext(tenant_id="t", user_id="u", domain_id="x")
    assert ctx.feature_enabled("any_flag") is False
    assert ctx.feature_enabled("any_flag", default=True) is True


def test_ctx_with_flags_derives_new() -> None:
    ctx = DomainContext(tenant_id="t", user_id="u", domain_id="x")
    ctx2 = ctx.with_flags(beta=True, canary=False)
    assert ctx2.feature_enabled("beta") is True
    assert ctx2.feature_enabled("canary") is False
    # original unchanged
    assert ctx.feature_enabled("beta") is False


def test_ctx_correlation_id_propagates() -> None:
    ctx = DomainContext(
        tenant_id="t", user_id="u", domain_id="x",
        correlation_id="fixed-123",
    )
    assert ctx.correlation_id == "fixed-123"


def test_ctx_user_id_optional() -> None:
    ctx = DomainContext(tenant_id="t", domain_id="x")
    assert ctx.user_id is None


# ============================================================================
# DomainRegistry - 6 tests
# ============================================================================

def test_registry_singleton() -> None:
    r1 = DomainRegistry.instance()
    r2 = DomainRegistry.instance()
    assert r1 is r2


def test_registry_has_5_domains() -> None:
    from app.domains import register_all
    registry = register_all()
    domains = registry.list_domains()
    ids = {d["domain_id"] for d in domains}
    assert ids >= {"fiscal_dz", "juridique", "logistique", "rh", "comptabilite"}


def test_registry_get_unknown_raises() -> None:
    r = DomainRegistry.instance()
    with pytest.raises(KeyError):
        r.get("nonexistent_domain")


def test_registry_get_latest_version() -> None:
    from app.domains import register_all
    r = register_all()
    d = r.get("fiscal_dz")
    assert d.version == "2026.01"


def test_registry_list_contains_operations() -> None:
    from app.domains import register_all
    register_all()
    r = DomainRegistry.instance()
    domains = r.list_domains()
    fiscal = next(d for d in domains if d["domain_id"] == "fiscal_dz")
    assert "calculate_irg" in fiscal["operations"]


def test_registry_deprecate() -> None:
    """Deprecate un domaine temporaire pour eviter de polluer le singleton."""
    from app.core.domain_engine import BaseDomain

    class TempDomain(BaseDomain):
        domain_id = "__test_deprecate_tmp__"
        version = "1.0.0"
        description = "temp"

        async def validate(self, input_data, ctx):  # type: ignore[override]
            return None  # noqa

        async def process(self, input_data, ctx):  # type: ignore[override]
            return None  # noqa

    r = DomainRegistry.instance()
    try:
        r.get("__test_deprecate_tmp__")
    except KeyError:
        r.register(TempDomain())

    r.deprecate("__test_deprecate_tmp__", "1.0.0")
    # Access specific version still works
    d = r.get("__test_deprecate_tmp__", "1.0.0")
    assert d is not None
    # List shows deprecated
    info = next(x for x in r.list_domains()
                 if x["domain_id"] == "__test_deprecate_tmp__")
    assert "1.0.0" in info["deprecated"]


# ============================================================================
# CELEvaluator - 15 tests
# ============================================================================

def test_cel_literal_int() -> None:
    e = CELEvaluator()
    assert e.evaluate("42", {}) == 42


def test_cel_literal_string() -> None:
    e = CELEvaluator()
    assert e.evaluate("'hello'", {}) == "hello"


def test_cel_literal_bool() -> None:
    e = CELEvaluator()
    assert e.evaluate("true", {}) is True
    assert e.evaluate("false", {}) is False


def test_cel_literal_null() -> None:
    e = CELEvaluator()
    assert e.evaluate("null", {}) is None


def test_cel_arithmetic() -> None:
    e = CELEvaluator()
    assert e.evaluate("2 + 3 * 4", {}) == 14
    assert e.evaluate("(2 + 3) * 4", {}) == 20
    assert e.evaluate("10 / 2", {}) == 5.0


def test_cel_comparison() -> None:
    e = CELEvaluator()
    assert e.evaluate("5 > 3", {}) is True
    assert e.evaluate("5 == 5", {}) is True
    assert e.evaluate("5 != 3", {}) is True
    assert e.evaluate("5 <= 5", {}) is True


def test_cel_logical_and_or_not() -> None:
    e = CELEvaluator()
    assert e.evaluate("true and false", {}) is False
    assert e.evaluate("true or false", {}) is True
    assert e.evaluate("not false", {}) is True


def test_cel_field_access() -> None:
    e = CELEvaluator()
    ctx = {"input": {"revenu": 100_000}}
    assert e.evaluate("input.revenu", ctx) == 100_000


def test_cel_nested_field() -> None:
    e = CELEvaluator()
    ctx = {"input": {"personne": {"nom": "Alice"}}}
    assert e.evaluate("input.personne.nom", ctx) == "Alice"


def test_cel_field_missing_returns_none() -> None:
    e = CELEvaluator()
    ctx = {"input": {}}
    assert e.evaluate("input.missing", ctx) is None


def test_cel_function_min_max() -> None:
    e = CELEvaluator()
    assert e.evaluate("min(3, 7)", {}) == 3
    assert e.evaluate("max(3, 7)", {}) == 7


def test_cel_function_contains() -> None:
    e = CELEvaluator()
    assert e.evaluate("contains('hello world', 'world')", {}) is True


def test_cel_unknown_function_raises() -> None:
    e = CELEvaluator()
    with pytest.raises(ValueError, match="Fonction inconnue"):
        e.evaluate("unknown_fn(1)", {})


def test_cel_invalid_expression() -> None:
    e = CELEvaluator()
    with pytest.raises(ValueError, match="Expression invalide"):
        e.evaluate("++--", {})


def test_cel_complex_expression() -> None:
    e = CELEvaluator()
    ctx = {"input": {"x": 10, "y": 20}}
    assert e.evaluate("input.x + input.y > 25", ctx) is True


# ============================================================================
# RulesEngine - 6 tests
# ============================================================================

def test_rules_engine_empty_bundle() -> None:
    re = RulesEngine()
    assert re.get_rules("unknown") == []


def test_rules_engine_load_simple() -> None:
    re = RulesEngine()
    rules = [Rule(id="r1", domain="test", when="true", compute={"x": 1})]
    re.load_bundle("test", rules)
    assert len(re.get_rules("test")) == 1


def test_rules_engine_priority_sort() -> None:
    re = RulesEngine()
    rules = [
        Rule(id="r_high", domain="test", priority=100, when="true", compute={"x": 1}),
        Rule(id="r_low", domain="test", priority=1, when="true", compute={"x": 2}),
    ]
    re.load_bundle("test", rules)
    ordered = re.get_rules("test")
    assert ordered[0].id == "r_low"  # plus prioritaire en premier


def test_rules_engine_evaluate_when() -> None:
    re = RulesEngine()
    re.load_bundle("test", [
        Rule(id="r", domain="test", when="input.x > 10", compute={"ok": True}),
    ])
    out = re.evaluate("test", {"input": {"x": 20}})
    assert out.get("ok") is True


def test_rules_engine_disabled_rule_skipped() -> None:
    re = RulesEngine()
    re.load_bundle("test", [
        Rule(id="r", domain="test", when="true",
             compute={"x": 1}, enabled=False),
    ])
    out = re.evaluate("test", {"input": {}})
    assert out.get("x") is None


def test_rules_engine_compute_expression() -> None:
    re = RulesEngine()
    re.load_bundle("test", [
        Rule(id="r", domain="test", when="true",
             compute={"double": "input.x * 2"}),
    ])
    out = re.evaluate("test", {"input": {"x": 21}})
    assert out["double"] == 42


# ============================================================================
# DomainRouter - 3 tests
# ============================================================================

async def test_router_process_success() -> None:
    from app.domains import register_all
    register_all()
    r = DomainRouter()
    ctx = DomainContext(
        tenant_id="t", user_id="u", domain_id="fiscal_dz",
        permissions=frozenset(["fiscal_dz:process"]),
    )
    res = await r.process({"revenu_annuel": 200_000}, ctx, "calculate_irg")
    assert res.success


async def test_router_process_forbidden() -> None:
    from app.domains import register_all
    register_all()
    r = DomainRouter()
    ctx = DomainContext(
        tenant_id="t", user_id="u", domain_id="fiscal_dz",
        permissions=frozenset(),  # no permission
    )
    res = await r.process({"revenu_annuel": 200_000}, ctx, "calculate_irg")
    assert not res.success
    assert any(i.code == "FORBIDDEN" for i in res.issues)


async def test_router_validate_unknown_domain() -> None:
    r = DomainRouter()
    ctx = DomainContext(
        tenant_id="t", user_id="u", domain_id="nonexistent",
        permissions=frozenset(["*"]),
    )
    with pytest.raises(KeyError):
        await r.validate({}, ctx)
