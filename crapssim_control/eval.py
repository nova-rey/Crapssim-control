# crapssim_control/eval.py
from __future__ import annotations

import ast
import math
from typing import Any, Dict, Optional


class EvalError(Exception):
    """Structured error raised by the safe evaluator."""

    def __init__(self, message: str, src: str | None = None, line: int | None = None, col: int | None = None):
        super().__init__(message)
        self.src = src
        self.line = line
        self.col = col

    def __str__(self) -> str:  # pragma: no cover (string form used in tests)
        base = super().__str__()
        if self.src:
            return f"{base}\n  in:\n{self.src}"
        return base


# ---- Safe evaluation configuration -------------------------------------------------

# Functions exposed to expressions
_SAFE_FUNCS: Dict[str, Any] = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "int": int,
    "float": float,
    "floor": math.floor,
    "ceil": math.ceil,
}

# Nodes we explicitly never allow (security)
_DISALLOWED_NODES = {
    ast.Attribute,
    ast.Subscript,
    ast.Lambda,
    ast.Dict,
    ast.List,
    ast.Set,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp if hasattr(ast, "DictComp") else ast.Dict,  # py-compat
    ast.GeneratorExp,
    ast.Await,
    ast.Yield,
    ast.With,
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.ClassDef,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.While,
    ast.For,
    ast.Try,
    ast.Raise,
    ast.Delete,
    ast.Assert,
}

# Expression AST whitelist
_ALLOWED_EXPR_NODES = {
    ast.Expression,
    ast.UnaryOp,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.Num,  # legacy constant
    ast.Constant,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.And,
    ast.Or,
    ast.BoolOp,
    ast.IfExp,  # ternary: a if cond else b
    ast.Call,   # restricted further below
    ast.Name,
    ast.Load,
}

# Statement AST whitelist (only for assignments)
_ALLOWED_STMT_NODES = _ALLOWED_EXPR_NODES | {
    ast.Module,
    ast.Assign,
    ast.AugAssign,
    ast.Store,
    ast.Expr,
}


def _assert_allowed(tree: ast.AST, allowed: set[type]) -> None:
    """Walk the AST and ensure only whitelisted nodes are present."""
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


def _eval_expr(src: str, ns: Dict[str, Any]) -> Any:
    """Compile and evaluate a safe *expression*."""
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
    except Exception as e:  # pragma: no cover - unexpected runtime error
        raise EvalError(f"{type(e).__name__}: {e}", src)


def _exec_statements(src: str, ns: Dict[str, Any]) -> None:
    """Compile and execute a restricted set of *statements* (assign/augassign)."""
    try:
        tree = ast.parse(src, mode="exec")
    except SyntaxError as e:
        raise EvalError("Syntax error", src, e.lineno, e.offset)

    _assert_allowed(tree, _ALLOWED_STMT_NODES)
    code = compile(tree, "<safe-eval>", "exec")
    exec(code, {"__builtins__": {}, **_SAFE_FUNCS}, ns)


# ---- Public API -------------------------------------------------------------------

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
        # Try pure expression first
        return _eval_expr(expr, ns)
    except EvalError as err:
        # Only fall back to statement execution if this looks like an assignment.
        try:
            tree = ast.parse(expr, mode="exec")
        except SyntaxError:
            # Not valid statements either -- keep the original EvalError surface
            raise err

        # Check for assignment nodes
        has_assignment = any(isinstance(n, (ast.Assign, ast.AugAssign)) for n in ast.walk(tree))
        if not has_assignment:
            # It's not an assignment; keep the original EvalError (e.g., undefined variable)
            raise err

        # Execute the (aug)assignment and sync back to state
        _assert_allowed(tree, _ALLOWED_STMT_NODES)
        code = compile(tree, "<safe-eval>", "exec")
        exec(code, {"__builtins__": {}, **_SAFE_FUNCS}, ns)

        # Sync mutated values (excluding safe funcs and builtins)
        for k, v in ns.items():
            if k in _SAFE_FUNCS or k == "__builtins__":
                continue
            state[k] = v
        return None


def eval_num(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> float | int:
    """
    Evaluate and ensure a numeric result. Raises EvalError if the result is non-numeric.
    Event overlay (if provided) takes precedence over state.
    """
    val = evaluate(expr, state, event)
    if isinstance(val, (int, float)):
        return val
    # allow numeric strings
    if isinstance(val, str):
        try:
            if "." in val:
                return float(val)
            return int(val)
        except ValueError:
            pass
    raise EvalError("Expression did not evaluate to a number", expr)


_TRUE_STRS = {"1", "true", "yes", "y", "on", "t"}
_FALSE_STRS = {"0", "false", "no", "n", "off", "f"}


def eval_bool(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> bool:
    """
    Evaluate and coerce to boolean with sensible string/number handling.
    """
    val = evaluate(expr, state, event)
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        s = val.strip().lower()
        if s in _TRUE_STRS:
            return True
        if s in _FALSE_STRS:
            return False
        # fallback: non-empty string is True
        return bool(s)
    return bool(val)


# Backwards-compat alias used by templates code
def safe_eval(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> Any:
    return evaluate(expr, state, event)