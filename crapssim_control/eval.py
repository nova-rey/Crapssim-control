# crapssim_control/eval.py
from __future__ import annotations

import ast
import math
import re
from types import MappingProxyType
from typing import Any, Dict, Optional


class EvalError(Exception):
    """Structured error raised by the safe evaluator."""

    def __init__(
        self, message: str, src: str | None = None, line: int | None = None, col: int | None = None
    ):
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
# Keep the surface area tight; add a few math helpers commonly needed in specs.
_SAFE_FUNCS: Dict[str, Any] = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "int": int,
    "float": float,
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": math.sqrt,
    "log": math.log,  # natural log
    "log10": math.log10,
}

# We disallow attribute/subscript so expressions remain simple and reproducible.
_DISALLOWED_NODES = {
    ast.Attribute,
    ast.Subscript,
    ast.Lambda,
    ast.Dict,
    ast.List,
    ast.Set,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp if hasattr(ast, "DictComp") else ast.Dict,
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
    ast.Num,
    ast.Constant,
    ast.Tuple,  # allow tuple literals (for `in (6,8)` style membership)
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,  # membership operator: a in (...)
    ast.NotIn,  # membership operator: a not in (...)
    ast.And,
    ast.Or,
    ast.BoolOp,
    ast.IfExp,
    ast.Call,
    ast.Name,
    ast.Load,
}

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
            if not isinstance(node.func, ast.Name):
                raise EvalError("Function calls on attributes or complex targets are not allowed")
            if node.func.id not in _SAFE_FUNCS:
                raise EvalError(f"Call to '{node.func.id}' is not allowed")


def _pretty_name_error_message(e: NameError) -> str:
    msg = e.args[0] if e.args else str(e)
    m = re.search(r"name '([^']+)' is not defined", msg)
    if m:
        var = m.group(1)
        return f"Unknown variable '{var}'"
    return "Unknown variable"


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
        raise EvalError(_pretty_name_error_message(e), src)
    except Exception as e:  # pragma: no cover
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


# ---- Namespace assembly -----------------------------------------------------------


def _freeze_mapping(maybe_dict: Optional[Dict[str, Any]]) -> MappingProxyType:
    """
    Present a read-only mapping to the eval namespace for documentation parity
    (indexing is blocked at AST level; this is mainly informational/defensive).
    """
    if isinstance(maybe_dict, dict):
        return MappingProxyType(dict(maybe_dict))
    return MappingProxyType({})


def _build_namespace(
    state: Optional[Dict[str, Any]], event: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Build the flat eval namespace.

    Notes:
      • We merge state first, then event, so event keys can override if needed.
      • We also include 'variables' and 'event' as read-only mappings for parity
        with docs, even though attribute/subscript access is intentionally blocked.
    """
    ns: Dict[str, Any] = {}

    # Flattened state (table cfg + user variables + controller snapshot)
    st = state or {}
    ns.update(st)

    # Flattened event keys
    ev = event or {}
    ns.update(ev)

    # Read-only 'variables' and 'event' views for clarity (non-indexable in expressions)
    variables_obj = st.get("variables") if isinstance(st.get("variables"), dict) else None
    # If variables are flattened in state (common), still provide an empty mapping here
    ns["variables"] = _freeze_mapping(variables_obj if variables_obj is not None else {})
    ns["event"] = _freeze_mapping(ev)

    return ns


# ---- Public API -------------------------------------------------------------------


def evaluate(
    expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None
) -> Any:
    """
    General evaluator with sandboxed namespace and structured errors.

    Supported operators:
      - arithmetic: + - * / // % **
      - comparisons: == != < <= > >=
      - boolean: and or not
      - membership: in, not in (with tuple literals)
      - ternary: A if cond else B
      - calls: only whitelisted helpers (min,max,abs,round,int,float,floor,ceil,sqrt,log,log10)

    Referencing values:
      - flat keys (recommended): e.g., point, rolls_since_point, on_comeout, type, roll
      - 'variables' and 'event' appear as read-only mappings for documentation parity,
        but indexing/attribute access is blocked by design.
    """
    ns = _build_namespace(state, event)

    try:
        return _eval_expr(expr, ns)
    except EvalError as err:
        # If it's not a simple expression, allow a tiny subset of statements (assign/augassign)
        try:
            tree = ast.parse(expr, mode="exec")
        except SyntaxError:
            raise err

        has_assignment = any(isinstance(n, (ast.Assign, ast.AugAssign)) for n in ast.walk(tree))
        if not has_assignment:
            raise err

        _assert_allowed(tree, _ALLOWED_STMT_NODES)
        code = compile(tree, "<safe-eval>", "exec")
        exec(code, {"__builtins__": {}, **_SAFE_FUNCS}, ns)

        # Propagate any new simple names back into state (best-effort)
        state = state or {}
        for k, v in ns.items():
            if k in _SAFE_FUNCS or k in ("__builtins__", "variables", "event"):
                continue
            state[k] = v
        return None


def eval_num(
    expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None
) -> float | int:
    """Evaluate and ensure a numeric result."""
    val = evaluate(expr, state, event)
    if isinstance(val, (int, float)):
        return val
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


def eval_bool(
    expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None
) -> bool:
    """Evaluate and coerce to boolean with sensible string/number handling."""
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
        return bool(s)
    return bool(val)


def safe_eval(
    expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None
) -> Any:
    """Backwards-compat alias used by templates code."""
    return evaluate(expr, state, event)


def try_eval(
    expr: str,
    state: Optional[Dict[str, Any]] = None,
    event: Optional[Dict[str, Any]] = None,
    default: Any = None,
) -> Any:
    """
    Fail-safe helper: evaluate expression but return `default` on EvalError.
    Ideal for templates and CSV logging where failure should not break flow.
    """
    try:
        return evaluate(expr, state, event)
    except EvalError:
        return default
