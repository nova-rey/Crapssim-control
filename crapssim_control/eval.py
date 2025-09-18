# crapssim_control/eval.py
from __future__ import annotations

import ast
import math
from typing import Any, Dict, Optional, Union

Number = Union[int, float]


class EvalError(Exception):
    def __init__(
        self,
        msg: str,
        expr: str,
        lineno: int | None = None,
        col: int | None = None,
    ) -> None:
        super().__init__(msg)
        self.expr = expr
        self.lineno = lineno
        self.col = col

    def __str__(self) -> str:
        loc = ""
        if self.lineno is not None and self.col is not None:
            loc = f" (at line {self.lineno}, col {self.col})"
        return f"{super().__str__()}{loc}\n  in: {self.expr}"


# --------- Safe helpers exposed to expressions ----------
SAFE_FUNCS: Dict[str, Any] = {
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "min": min,
    "max": max,
    "abs": abs,
    "int": int,
    "float": float,
}

# --------- Allowed node sets (tight, explicit) ----------
_ALLOWED_EXPR_NODES = {
    ast.Expression, ast.UnaryOp, ast.BinOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Name, ast.Load, ast.Constant, ast.Dict, ast.List, ast.Tuple,
    ast.Subscript, ast.Slice, ast.Attribute, ast.Call,

    ast.And, ast.Or, ast.Not,
    ast.USub, ast.UAdd,

    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,

    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
}

# For statements we only allow assignment/augassign whose RHS is itself a safe expression.
_ALLOWED_STMT_NODES = {
    ast.Module, ast.Assign, ast.AugAssign, ast.Store, ast.Name, ast.Expr,

    ast.UnaryOp, ast.BinOp, ast.BoolOp, ast.Compare, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,

    ast.IfExp, ast.Tuple, ast.List, ast.Dict, ast.Subscript, ast.Slice,
    ast.Load,
}


def _assert_allowed(node: ast.AST, allowed: set[type]) -> None:
    for child in ast.walk(node):
        if type(child) not in allowed:
            raise EvalError(
                f"Disallowed syntax: {type(child).__name__}",
                "",
                getattr(child, "lineno", None),
                getattr(child, "col_offset", None),
            )


def _assert_calls_safe(tree: ast.AST) -> None:
    """
    Ensure any Call nodes only target names present in SAFE_FUNCS.
    """
    for child in ast.walk(tree):
        if isinstance(child, ast.Call):
            # Only allow simple function names like round(...), ceil(...)
            if isinstance(child.func, ast.Name):
                func_name = child.func.id
            else:
                # attributes, subscripts, lambdas, etc. are not allowed
                raise EvalError(f"Call not allowed", "", getattr(child, "lineno", None), getattr(child, "col_offset", None))
            if func_name not in SAFE_FUNCS:
                # phrase expected by tests: "not allowed"
                raise EvalError(f"Call to '{func_name}' not allowed", "", getattr(child, "lineno", None), getattr(child, "col_offset", None))


def _merge_locals(state: Optional[Dict[str, Any]], event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Event overlay wins if same key exists (tests rely on this behavior).
    """
    merged: Dict[str, Any] = {}
    if state:
        merged.update(state)
    if event:
        merged.update(event)
        merged["event"] = event
    return merged


# ---------------- Public API ----------------

def evaluate(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> Any:
    """
    Safe evaluator used by rules:
      - First try to parse as an EXPRESSION
      - If that fails (SyntaxError), parse as simple STATEMENTS (Assign / AugAssign)
    Mutates `state` in-place to reflect changes. Returns expression value (or None for exec).
    """
    if not isinstance(expr, str):
        raise EvalError("Expression must be a string", str(expr))

    local_ns = _merge_locals(state, event)

    # 1) Expression mode
    try:
        tree = ast.parse(expr, mode="eval")
        _assert_allowed(tree, _ALLOWED_EXPR_NODES)
        _assert_calls_safe(tree)
        code = compile(tree, "<eval>", "eval")
        try:
            result = eval(code, {"__builtins__": {}, **SAFE_FUNCS}, local_ns)
        except NameError as ne:
            name = getattr(ne, "name", None)
            if name:
                raise EvalError(f"Unknown variable '{name}'", expr)
            raise EvalError(f"Unknown variable", expr)
        # propagate locals (for container mutations)
        if isinstance(state, dict):
            state.clear()
            state.update({k: v for k, v in local_ns.items() if k != "event"})
        return result
    except SyntaxError:
        pass  # fall through to exec
    except EvalError:
        raise
    except Exception as ex:
        raise EvalError(f"Runtime error: {ex}", expr)

    # 2) Statement mode (supports x = ..., x += ..., etc.)
    try:
        tree = ast.parse(expr, mode="exec")
    except SyntaxError as se:
        raise EvalError(f"Syntax error: {se.msg}", expr, se.lineno, se.offset)
    _assert_allowed(tree, _ALLOWED_STMT_NODES)
    # additionally, make sure any expressions used inside statements also obey the call whitelist
    _assert_calls_safe(tree)

    try:
        code = compile(tree, "<exec>", "exec")
        exec(code, {"__builtins__": {}, **SAFE_FUNCS}, local_ns)
    except NameError as ne:
        name = getattr(ne, "name", None)
        if name:
            raise EvalError(f"Unknown variable '{name}'", expr)
        raise EvalError("Unknown variable", expr)
    except Exception as ex:
        raise EvalError(f"Runtime error: {ex}", expr)

    if isinstance(state, dict):
        state.clear()
        state.update({k: v for k, v in local_ns.items() if k != "event"})
    return None


def safe_eval(expr: str, state: Optional[Dict[str, Any]] = None) -> Any:
    """
    Legacy helper used by templates: expression-only evaluation.
    """
    if not isinstance(expr, str):
        raise EvalError("Expression must be a string", str(expr))

    local_ns = dict(state or {})
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as se:
        raise EvalError(f"Syntax error: {se.msg}", expr, se.lineno, se.offset)

    _assert_allowed(tree, _ALLOWED_EXPR_NODES)
    _assert_calls_safe(tree)

    try:
        code = compile(tree, "<safe_eval>", "eval")
        result = eval(code, {"__builtins__": {}, **SAFE_FUNCS}, local_ns)
        if isinstance(state, dict):
            state.clear()
            state.update(local_ns)
        return result
    except NameError as ne:
        name = getattr(ne, "name", None)
        if name:
            raise EvalError(f"Unknown variable '{name}'", expr)
        raise EvalError("Unknown variable", expr)
    except Exception as ex:
        raise EvalError(f"Runtime error: {ex}", expr)


def eval_num(expr: Any, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> Number:
    """
    Evaluate and coerce to a number (int/float). Supports event overlay.
    """
    if isinstance(expr, (int, float)):
        return float(expr) if isinstance(expr, float) else int(expr)

    # Use expression-only path so arbitrary statements aren't accepted here.
    merged = _merge_locals(state or {}, event or {})
    val = safe_eval(str(expr), merged)

    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, (int, float)):
        return float(val) if isinstance(val, float) else int(val)
    if isinstance(val, str):
        s = val.strip().lower()
        try:
            if "." in s:
                return float(s)
            return int(s)
        except ValueError:
            pass
    raise EvalError("Not a numeric expression", str(expr))


def eval_bool(expr: Any, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> bool:
    """
    Evaluate and coerce to boolean. Supports event overlay and common string coercions.
    """
    if isinstance(expr, bool):
        return expr

    merged = _merge_locals(state or {}, event or {})
    val = safe_eval(str(expr), merged)

    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        s = val.strip().lower()
        if s in {"", "0", "false", "no", "off"}:
            return False
        if s in {"1", "true", "yes", "on"}:
            return True
        # non-empty strings default truthy
        return True
    return bool(val)