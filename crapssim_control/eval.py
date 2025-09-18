# crapssim_control/eval.py

from __future__ import annotations
from typing import Any, Dict, Optional
import ast
from math import floor, ceil  # allowed pure helpers

__all__ = ["evaluate", "safe_eval", "eval_num", "eval_bool", "EvalError"]


class EvalError(Exception):
    def __init__(self, msg: str, src: str = "", lineno: int | None = None, col: int | None = None):
        super().__init__(msg)
        self.src = src
        self.lineno = lineno
        self.col = col

    def __str__(self) -> str:
        loc = ""
        if self.lineno is not None and self.col is not None:
            loc = f" (at line {self.lineno}, col {self.col})"
        if self.src:
            return f"{super().__str__()}{loc}\n  in:\n{self.src}"
        return f"{super().__str__()}{loc}"


# --- Allowed / disallowed node sets -----------------------------------------

_ALLOWED_EXPR_NODES = {
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.BinOp, ast.UnaryOp, ast.BoolOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.And, ast.Or, ast.Not,
    ast.USub, ast.UAdd,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.IfExp,
    ast.Tuple, ast.List, ast.Dict,  # literal construction only
    ast.Load, ast.Store,
    ast.Call,  # gated to SAFE_FUNCS only
}

_ALLOWED_STMT_NODES = {
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign,
    ast.Name,
    ast.Store, ast.Load,
    ast.BinOp, ast.UnaryOp, ast.BoolOp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.And, ast.Or, ast.Not,
    ast.USub, ast.UAdd,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.IfExp,
    ast.Tuple, ast.List, ast.Dict,
    ast.Constant,
    ast.Call,  # gated to SAFE_FUNCS only
}

_DISALLOWED_NODES = {
    ast.Attribute,      # a.b
    ast.Subscript,      # a[0]
    ast.Slice, ast.ExtSlice,
    ast.Lambda, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp,
    ast.With, ast.Raise, ast.Try, ast.While, ast.For, ast.AsyncFor, ast.AsyncWith,
    ast.FunctionDef, ast.AsyncFunctionDef,
    ast.ClassDef, ast.AnnAssign, ast.Delete, ast.Import, ast.ImportFrom,
    ast.Global, ast.Nonlocal,
    ast.Yield, ast.YieldFrom, ast.Await, ast.Match,
}

# Tiny whitelist of pure, deterministic builtins
_SAFE_FUNCS = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "int": int,
    "float": float,
    "floor": floor,
    "ceil": ceil,
}


def _assert_allowed(tree: ast.AST, allowed: set[type]) -> None:
    for node in ast.walk(tree):
        t = type(node)
        if t in _DISALLOWED_NODES:
            raise EvalError(f"Disallowed syntax: {t.__name__}")
        if t not in allowed:
            raise EvalError(f"Disallowed syntax: {t.__name__}")
        if isinstance(node, ast.Call):
            # Only allow simple name calls to whitelisted functions
            if not isinstance(node.func, ast.Name):
                raise EvalError("Function calls on attributes or complex targets are not allowed")
            if node.func.id not in _SAFE_FUNCS:
                raise EvalError(f"Call to '{node.func.id}' is not allowed")


def _exec_statements(src: str, ns: Dict[str, Any]) -> None:
    try:
        tree = ast.parse(src, mode="exec")
    except SyntaxError as e:
        raise EvalError("Syntax error", src, e.lineno, e.offset)

    _assert_allowed(tree, _ALLOWED_STMT_NODES)
    code = compile(tree, "<safe-eval>", "exec")
    exec(code, {"__builtins__": {}, **_SAFE_FUNCS}, ns)


def _eval_expr(src: str, ns: Dict[str, Any]) -> Any:
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise EvalError("Syntax error", src, e.lineno, e.offset)

    _assert_allowed(tree, _ALLOWED_EXPR_NODES)
    code = compile(tree, "<safe-eval>", "eval")
    try:
        return eval(code, {"__builtins__": {}, **_SAFE_FUNCS}, ns)
    except NameError as e:
        # Normalize to EvalError for tests
        raise EvalError(str(e), src)


def evaluate(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> Any:
    """
    General evaluator.

    - If `expr` is an expression: returns its value (no state mutation).
    - If `expr` is assignment/augassign: executes it and returns None (mutates `state`).
    - Strictly blocks attributes, subscripts, loops, imports, etc.
    - Allows only calls to SAFE_FUNCS (min, max, abs, round, int, float, floor, ceil).

    Namespace precedence: state first, then event overlays (event wins).
    """
    ns: Dict[str, Any] = {}
    state = state or {}
    # state first...
    ns.update(state)
    # ...then event overlays take precedence
    if event:
        ns.update(event)

    try:
        result = _eval_expr(expr, ns)
        return result
    except EvalError:
        # Not a pure expression (or blocked in expr mode): try as a statement
        _exec_statements(expr, ns)
        # Sync simple names back into state (skip SAFE_FUNCS and __builtins__)
        for k, v in ns.items():
            if k in _SAFE_FUNCS or k == "__builtins__":
                continue
            state[k] = v
        return None


# --- Back-compat helpers used by legacy modules/tests ------------------------

def safe_eval(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> Any:
    """Back-compat shim delegating to `evaluate`."""
    return evaluate(expr, state=state, event=event)


def _merge_ns(state: Optional[Dict[str, Any]], event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ns: Dict[str, Any] = {}
    if state:
        ns.update(state)
    if event:
        ns.update(event)  # event wins
    return ns


def eval_num(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> float:
    """Evaluate a numeric expression only (no statements). Returns float."""
    ns = _merge_ns(state, event)
    val = _eval_expr(expr, ns)
    try:
        return float(val)
    except (TypeError, ValueError):
        raise EvalError("Expression did not produce a number", expr)


_FALSEY_STRS = {"false", "no", "off", "0", "f", "n"}
_TRUTHY_STRS = {"true", "yes", "on", "1", "t", "y"}


def eval_bool(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> bool:
    """Evaluate a boolean expression only (no statements). Returns bool with friendly string coercion."""
    ns = _merge_ns(state, event)
    val = _eval_expr(expr, ns)
    if isinstance(val, str):
        s = val.strip().lower()
        if s in _FALSEY_STRS:
            return False
        if s in _TRUTHY_STRS:
            return True
    return bool(val)