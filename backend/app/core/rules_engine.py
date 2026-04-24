"""Rules engine YAML-driven avec evaluateur expression subset-CEL.

Expression subset supportee :
    - Literals : int, float, string, bool, null
    - Fields  : input.foo, input.foo.bar
    - Comparaisons : ==, !=, <, <=, >, >=
    - Logique : and, or, not
    - Arithmetique : +, -, *, /, %, min(a,b), max(a,b)
    - Funcs registered : in, contains, startswith, endswith

Format regle YAML :
    id: rule_irg_tranche_1
    domain: fiscal_dz
    version: 2026.01
    description: "IRG tranche 0-10000 exonere"
    when: 'input.revenu_annuel <= 120000'
    compute:
      tax_amount: 0
      tranche: 1
    priority: 10
    enabled: true
"""
from __future__ import annotations

import ast
import logging
import operator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("uba.core.rules_engine")


# ============================================================================
# Rule model (Pydantic)
# ============================================================================

class Rule(BaseModel):
    """Regle metier externalisee YAML."""

    model_config = ConfigDict(extra="forbid")

    id: str
    domain: str
    version: str = "1.0.0"
    description: str = ""
    when: str = Field(default="true",
                       description="Expression booleenne : condition de declenchement")
    compute: dict[str, Any] = Field(default_factory=dict,
                                     description="Valeurs calculees/assignees")
    validate_expr: str | None = Field(None, alias="validate",
                                      description="Expression -> bool si specifiee")
    guard: str | None = Field(None, description="Pre-condition hard (raise si false)")
    priority: int = Field(default=100, description="Plus petit = plus prioritaire")
    enabled: bool = True


# ============================================================================
# CEL subset evaluator (safe, no eval())
# ============================================================================

_COMPARATORS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
}

_BOOLOPS = {ast.And: all, ast.Or: any}
_UNARYOPS = {ast.Not: operator.not_, ast.USub: operator.neg, ast.UAdd: operator.pos}


class CELEvaluator:
    """Evaluateur expressions subset-CEL securise (AST walk, pas d'eval)."""

    def __init__(self, functions: dict[str, Callable[..., Any]] | None = None) -> None:
        self.functions = {
            "min": min, "max": max, "abs": abs, "len": len,
            "sum": sum, "round": round,
            "contains": lambda s, sub: sub in s,
            "startswith": lambda s, prefix: str(s).startswith(str(prefix)),
            "endswith": lambda s, suffix: str(s).endswith(str(suffix)),
            "lower": lambda s: str(s).lower(),
            "upper": lambda s: str(s).upper(),
        }
        if functions:
            self.functions.update(functions)

    def evaluate(self, expression: str, context: dict[str, Any]) -> Any:
        """Evalue une expression dans le contexte donne. Lance ValueError si
        expression invalide ou non-supportee."""
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Expression invalide: {expression!r} ({exc})") from exc
        return self._eval(tree.body, context)

    def _eval(self, node: ast.AST, ctx: dict[str, Any]) -> Any:  # noqa: C901 - dispatcher
        # Literals
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            # true/false/null keywords (CEL syntax)
            if node.id == "true":
                return True
            if node.id == "false":
                return False
            if node.id in ("null", "none"):
                return None
            if node.id in ctx:
                return ctx[node.id]
            raise ValueError(f"Nom inconnu: {node.id}")
        # Field access : input.foo.bar
        if isinstance(node, ast.Attribute):
            obj = self._eval(node.value, ctx)
            if isinstance(obj, dict):
                return obj.get(node.attr)
            return getattr(obj, node.attr, None)
        # Index : arr[0], dict['key']
        if isinstance(node, ast.Subscript):
            obj = self._eval(node.value, ctx)
            idx = self._eval(node.slice, ctx)
            try:
                return obj[idx]
            except (KeyError, IndexError, TypeError):
                return None
        # Comparisons : a == b, a < b, a in [1,2]
        if isinstance(node, ast.Compare):
            left = self._eval(node.left, ctx)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator, ctx)
                fn = _COMPARATORS.get(type(op))
                if fn is None:
                    raise ValueError(f"Comparateur non supporte: {type(op).__name__}")
                if not fn(left, right):
                    return False
                left = right
            return True
        # Bool ops : a and b, a or b
        if isinstance(node, ast.BoolOp):
            fn = _BOOLOPS.get(type(node.op))
            if fn is None:
                raise ValueError(f"BoolOp non supporte: {type(node.op).__name__}")
            return fn(self._eval(v, ctx) for v in node.values)
        # Unary ops : not x, -x
        if isinstance(node, ast.UnaryOp):
            fn = _UNARYOPS.get(type(node.op))
            if fn is None:
                raise ValueError(f"UnaryOp non supporte: {type(node.op).__name__}")
            return fn(self._eval(node.operand, ctx))
        # Binary ops : a + b, a * b
        if isinstance(node, ast.BinOp):
            fn = _BINOPS.get(type(node.op))
            if fn is None:
                raise ValueError(f"BinOp non supporte: {type(node.op).__name__}")
            return fn(self._eval(node.left, ctx), self._eval(node.right, ctx))
        # Function call
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Seules les fonctions par nom sont supportees")
            fn = self.functions.get(node.func.id)
            if fn is None:
                raise ValueError(f"Fonction inconnue: {node.func.id}")
            args = [self._eval(a, ctx) for a in node.args]
            return fn(*args)
        # List / Tuple literals
        if isinstance(node, ast.List | ast.Tuple):
            return [self._eval(e, ctx) for e in node.elts]
        # Dict literal
        if isinstance(node, ast.Dict):
            return {
                self._eval(k, ctx): self._eval(v, ctx)
                for k, v in zip(node.keys, node.values)
                if k is not None
            }
        raise ValueError(f"Type AST non supporte: {type(node).__name__}")


# ============================================================================
# RulesLoader + RulesEngine
# ============================================================================

@dataclass
class RulesBundle:
    """Rules chargees pour un domaine."""
    domain: str
    rules: list[Rule] = field(default_factory=list)
    loaded_at: str = ""


class RulesEngine:
    """Execute un ensemble de regles sur un contexte donne."""

    def __init__(
        self, evaluator: CELEvaluator | None = None,
    ) -> None:
        self.evaluator = evaluator or CELEvaluator()
        self._bundles: dict[str, RulesBundle] = {}

    def load_bundle(self, domain: str, rules: list[Rule]) -> None:
        """Charge un bundle de regles pour un domaine."""
        bundle = RulesBundle(domain=domain, rules=sorted(rules, key=lambda r: r.priority))
        self._bundles[domain] = bundle
        logger.info("loaded %d rules for domain %s", len(rules), domain)

    def get_rules(self, domain: str) -> list[Rule]:
        bundle = self._bundles.get(domain)
        return bundle.rules if bundle else []

    def evaluate(
        self, domain: str, context: dict[str, Any],
    ) -> dict[str, Any]:
        """Applique toutes les rules enabled du domaine et merge computes."""
        output: dict[str, Any] = {}
        applied: list[str] = []
        for rule in self.get_rules(domain):
            if not rule.enabled:
                continue
            try:
                # Merge current output into context for chainable rules
                eval_ctx = {**context, "output": output}
                if rule.when and not self.evaluator.evaluate(rule.when, eval_ctx):
                    continue
                if rule.guard and not self.evaluator.evaluate(rule.guard, eval_ctx):
                    raise ValueError(f"Rule {rule.id} guard failed")
                for k, v in rule.compute.items():
                    # v peut etre une valeur brute ou une expression (string qui parse)
                    if isinstance(v, str) and _looks_like_expression(v):
                        try:
                            output[k] = self.evaluator.evaluate(v, eval_ctx)
                            continue
                        except Exception:
                            pass  # Fallback : valeur litterale
                    output[k] = v
                applied.append(rule.id)
            except Exception as exc:
                logger.warning("rule %s failed: %s", rule.id, exc)
        output["_rules_applied"] = applied
        return output


def _looks_like_expression(s: str) -> bool:
    """Heuristique simple : contient des operators/dots pour eviter d'evaluer
    les strings litterales."""
    markers = ("input.", "output.", "==", "!=", "<", ">", "+", "-", "*", "/",
               " and ", " or ", "(", "min(", "max(", "abs(")
    return any(m in s for m in markers)


# ============================================================================
# YAML loader
# ============================================================================

def load_rules_from_dir(base_dir: Path | str) -> dict[str, list[Rule]]:
    """Charge toutes les rules YAML depuis base_dir/{domain}/*.yaml.

    Retourne dict[domain, list[Rule]]. Chaque fichier YAML peut contenir
    soit 1 rule (dict racine), soit N rules (list racine ou key 'rules').
    """
    base = Path(base_dir)
    if not base.exists():
        logger.warning("rules dir not found: %s", base)
        return {}
    by_domain: dict[str, list[Rule]] = {}
    for domain_dir in sorted(base.iterdir()):
        if not domain_dir.is_dir():
            continue
        domain = domain_dir.name
        rules: list[Rule] = []
        for f in sorted(domain_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(f.read_text(encoding="utf-8"))
                rules.extend(_parse_rules_file(raw, domain, f.name))
            except Exception as exc:
                logger.error("failed to load %s: %s", f, exc)
        if rules:
            by_domain[domain] = rules
            logger.info("loaded %d rules for domain %s from %s",
                        len(rules), domain, domain_dir)
    return by_domain


def _parse_rules_file(raw: Any, domain: str, filename: str) -> list[Rule]:
    """Parse un fichier YAML (rule unique, liste, ou {'rules': [...]})."""
    if raw is None:
        return []
    if isinstance(raw, dict) and "rules" in raw and isinstance(raw["rules"], list):
        return [_build_rule(r, domain) for r in raw["rules"]]
    if isinstance(raw, list):
        return [_build_rule(r, domain) for r in raw]
    if isinstance(raw, dict):
        return [_build_rule(raw, domain)]
    raise ValueError(f"Unexpected rules format in {filename}")


def _build_rule(data: dict[str, Any], domain: str) -> Rule:
    data.setdefault("domain", domain)
    return Rule(**data)
