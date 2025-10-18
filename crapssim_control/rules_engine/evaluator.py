"""Deterministic evaluator for whitelisted rule expressions."""

from __future__ import annotations

import ast
import operator
from typing import Any, Dict, List

SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.BitXor: operator.xor,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Not: operator.not_,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

SAFE_VARS = {
    "bankroll_after",
    "drawdown_after",
    "hand_id",
    "roll_in_hand",
    "point_on",
    "last_roll_total",
    "box_hits",
    "dc_losses",
    "dc_wins",
}


def _eval_expr(expr: str, context: Dict[str, Any]) -> Any:
    """Evaluate a simple expression safely using whitelisted names."""

    safe_context = {k: context[k] for k in context if k in SAFE_VARS}

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Num):  # pragma: no cover - Py<3.8 compatibility
            return node.n
        if isinstance(node, ast.Name):
            if node.id not in SAFE_VARS:
                raise ValueError(f"Unknown var: {node.id}")
            if node.id not in safe_context:
                raise ValueError(f"Unknown var: {node.id}")
            return safe_context[node.id]
        if isinstance(node, ast.UnaryOp):
            op = SAFE_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported unary op: {ast.dump(node)}")
            return op(_eval(node.operand))
        if isinstance(node, ast.BinOp):
            op = SAFE_OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported binary op: {ast.dump(node.op)}")
            return op(_eval(node.left), _eval(node.right))
        if isinstance(node, ast.BoolOp):
            values = [_eval(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            if isinstance(node.op, ast.Or):
                return any(values)
            raise ValueError(f"Unsupported boolean op: {ast.dump(node.op)}")
        if isinstance(node, ast.Subscript):
            base = _eval(node.value)
            if isinstance(node.slice, ast.Constant):
                key = node.slice.value
            elif hasattr(ast, "Index") and isinstance(node.slice, ast.Index):  # pragma: no cover
                key = _eval(node.slice.value)
            else:
                raise ValueError(f"Unsupported subscript: {ast.dump(node.slice)}")
            if isinstance(base, (list, tuple)):
                return base[int(key)]
            if isinstance(base, dict):
                return base[key]
            raise ValueError("Subscript base must be list, tuple, or dict")
        if isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op_node, right_node in zip(node.ops, node.comparators):
                op = SAFE_OPS.get(type(op_node))
                if op is None:
                    raise ValueError(f"Unsupported comparator: {ast.dump(op_node)}")
                right = _eval(right_node)
                if not op(left, right):
                    return False
                left = right
            return True
        raise ValueError(f"Unsupported expression: {ast.dump(node)}")

    try:
        expr_ast = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(str(exc)) from exc

    return _eval(expr_ast.body)


def evaluate_rules(rules: List[Dict[str, Any]], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return list of rule evaluations with fired=True/False."""

    results: List[Dict[str, Any]] = []
    safe_context = {k: context[k] for k in context if k in SAFE_VARS and context[k] is not None}

    for rule in rules or []:
        rule_id = rule.get("id")
        if not rule.get("enabled", True):
            results.append({"rule_id": rule_id, "fired": False, "reason": "disabled"})
            continue
        try:
            when_expr = str(rule.get("when", "False"))
            when_val = bool(_eval_expr(when_expr, safe_context))
            guard_val = True
            guard_expr = rule.get("guard")
            if guard_expr:
                guard_val = bool(_eval_expr(str(guard_expr), safe_context))
            fired = bool(when_val and guard_val)
            results.append(
                {
                    "rule_id": rule_id,
                    "fired": fired,
                    "vars": {k: safe_context.get(k) for k in SAFE_VARS if k in safe_context},
                }
            )
        except Exception as exc:  # noqa: BLE001 - deterministic logging of errors
            results.append({"rule_id": rule_id, "fired": False, "error": str(exc)})
    return results
