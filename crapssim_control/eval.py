# crapssim_control/eval.py
from __future__ import annotations

import ast
from typing import Any, Dict, Optional, Union


Number = Union[int, float]


class EvalError(Exception):
    def __init__(self, msg: str, expr: str, lineno: int | None = None, col: int | None = None) -> None:
        super().__init__(msg)
        self.expr = expr
        self.lineno = lineno
        self.col = col

    def __str__(self) -> str:
        loc = ""
        if self.lineno is not None and self.col is not None:
            loc = f" (at line {self.lineno}, col {self.col})"
        return f"{super().__str__()}{loc}\n  in: {self.expr}"


# ---------- Allowed node sets (tight but practical) ----------

_ALLOWED_EXPR_NODES = {
    ast.Expression, ast.UnaryOp, ast.BinOp, ast.BoolOp, ast.Compare, ast.Call,
    ast.Name, ast.Load, ast.Constant, ast.IfExp, ast.Dict, ast.List, ast.Tuple,
    ast.Subscript, ast.Slice, ast.Attribute,

    ast.And, ast.Or, ast.Not,
    ast.USub, ast.UAdd,

    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,

    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
}

_ALLOWED_STMT_NODES = {
    ast.Module, ast.Assign, ast.AugAssign, ast.Store, ast.Name, ast.Expr,

    ast.UnaryOp, ast.BinOp, ast.BoolOp, ast.Compare, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,

    ast.IfExp, ast.Tuple, ast.List, ast.Dict, ast.Subscript, ast.Slice,
}


def _assert_allowed(node: ast.AST, allowed: set[type]) -> None:
    for child in ast.walk(node):
        if type(child) not in allowed:
            raise EvalError(f"Disallowed syntax: {type(child).__name__}", "", getattr(child, "lineno", None), getattr(child, "col_offset", None))


# ---------- Public API expected by tests ----------

def evaluate(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> Any:
    """
    Safe-ish evaluator used by rules:
      - First try to parse as an EXPRESSION (mode='eval')
      - If that fails with SyntaxError, parse as simple STATEMENTS (Assign / AugAssign) with mode='exec'
    Mutates `state` as its local namespace, returns the eval/exec result (None for exec).
    """
    if not isinstance(expr, str):
        raise EvalError("Expression must be a string", str(expr))

    # locals the expression can see/mutate
    local_ns = dict(state or {})
    if event is not None:
        local_ns["event"] = event

    # 1) Try expression mode
    try:
        tree = ast.parse(expr, mode="eval")
        _assert_allowed(tree, _ALLOWED_EXPR_NODES)
        code = compile(tree, "<eval>", "eval")
        result = eval(code, {"__builtins__": {}}, local_ns)
        # push back locals only for simple expressions that may mutate containers
        if isinstance(state, dict):
            state.clear()
            state.update(local_ns)
        return result
    except SyntaxError:
        pass  # fall through to exec
    except EvalError:
        raise
    except Exception as ex:
        raise EvalError(f"Runtime error: {ex}", expr)

    # 2) Statement mode (supports: x = ..., x += ..., etc.)
    try:
        tree = ast.parse(expr, mode="exec")
    except SyntaxError as se:
        raise EvalError(f"Syntax error: {se.msg}", expr, se.lineno, se.offset)
    _assert_allowed(tree, _ALLOWED_STMT_NODES)

    try:
        code = compile(tree, "<exec>", "exec")
        exec(code, {"__builtins__": {}}, local_ns)
    except Exception as ex:
        raise EvalError(f"Runtime error: {ex}", expr)

    if isinstance(state, dict):
        state.clear()
        state.update(local_ns)
    return None


def safe_eval(expr: str, state: Optional[Dict[str, Any]] = None) -> Any:
    """
    Legacy helper used by templates: expression-only evaluation.
    Raises EvalError if the string isn't a pure expression (e.g., contains assignment).
    """
    if not isinstance(expr, str):
        raise EvalError("Expression must be a string", str(expr))

    local_ns = dict(state or {})
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as se:
        # templates only expect expressions; treat assignment as syntax error here
        raise EvalError(f"Syntax error: {se.msg}", expr, se.lineno, se.offset)

    _assert_allowed(tree, _ALLOWED_EXPR_NODES)
    try:
        code = compile(tree, "<safe_eval>", "eval")
        result = eval(code, {"__builtins__": {}}, local_ns)
        # propagate any container mutations back
        if isinstance(state, dict):
            state.clear()
            state.update(local_ns)
        return result
    except Exception as ex:
        raise EvalError(f"Runtime error: {ex}", expr)


def eval_num(expr: Any, state: Optional[Dict[str, Any]] = None) -> Number:
    """
    Evaluate and coerce to a number (int/float). Used for amounts in templates.
    """
    # Already numeric
    if isinstance(expr, (int, float)):
        return float(expr) if isinstance(expr, float) else int(expr)

    val = safe_eval(str(expr), state)
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, (int, float)):
        return float(val) if isinstance(val, float) else int(val)
    # try numeric-ish strings
    if isinstance(val, str):
        s = val.strip()
        try:
            if "." in s:
                return float(s)
            return int(s)
        except ValueError:
            pass
    raise EvalError("Not a numeric expression", str(expr))


def eval_bool(expr: Any, state: Optional[Dict[str, Any]] = None) -> bool:
    """
    Evaluate and coerce to boolean.
    """
    if isinstance(expr, bool):
        return expr
    val = safe_eval(str(expr), state)
    return bool(val)