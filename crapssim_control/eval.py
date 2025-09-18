# crapssim_control/eval.py

from __future__ import annotations
from typing import Any, Dict, Optional
import ast

__all__ = ["evaluate", "EvalError"]


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


# Strict AST allowlist
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
    ast.Tuple, ast.List, ast.Dict,  # construction is fine; indexing is not
    ast.Load, ast.Store,
    ast.Call,  # function calls are allowed but only to SAFE_FUNCS (checked separately)
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
    ast.Call,  # gated below
}

# Hard NOs (explicit to be safe)
_DISALLOWED_NODES = {
    ast.Attribute,   # obj.attr
    ast.Subscript,   # a[0]
    ast.Slice, ast.ExtSlice,
    ast.Lambda, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp,
    ast.With, ast.Raise, ast.Try, ast.While, ast.For, ast.AsyncFor, ast.AsyncWith, ast.FunctionDef,
    ast.ClassDef, ast.AnnAssign, ast.Delete, ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
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
}


def _assert_allowed(tree: ast.AST, allowed: set[type]) -> None:
    for node in ast.walk(tree):
        t = type(node)
        if t in _DISALLOWED_NODES:
            raise EvalError(f"Disallowed syntax: {t.__name__}")
        if t not in allowed:
            raise EvalError(f"Disallowed syntax: {t.__name__}")
        # Gate function calls to SAFE_FUNCS only
        if isinstance(node, ast.Call):
            # Only allow calls like name(args...)
            if not isinstance(node.func, ast.Name):
                raise EvalError("Function calls on attributes or complex targets are not allowed")
            if node.func.id not in _SAFE_FUNCS:
                raise EvalError(f"Call to '{node.func.id}' is not allowed")


def _exec_statements(src: str, ns: Dict[str, Any]) -> Any:
    try:
        tree = ast.parse(src, mode="exec")
    except SyntaxError as e:
        raise EvalError("Syntax error", src, e.lineno, e.offset)

    _assert_allowed(tree, _ALLOWED_STMT_NODES)
    code = compile(tree, "<safe-eval>", "exec")
    # Never expose real builtins
    exec(code, {"__builtins__": {} , **_SAFE_FUNCS}, ns)
    return None


def _eval_expr(src: str, ns: Dict[str, Any]) -> Any:
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        raise EvalError("Syntax error", src, e.lineno, e.offset)

    _assert_allowed(tree, _ALLOWED_EXPR_NODES)
    code = compile(tree, "<safe-eval>", "eval")
    return eval(code, {"__builtins__": {}, **_SAFE_FUNCS}, ns)


def evaluate(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> Any:
    """
    Safely evaluate/execute a tiny expression language.

    - Mutates `state` for Assign/AugAssign (e.g., `units = 10`, `units += 5`).
    - Returns the value of a pure expression when `expr` is an expression.
    - For statements, returns None.

    Forbidden:
      * Attribute access (a.b)
      * Subscripts / indexing (a[0])
      * Any function call except whitelisted SAFE_FUNCS
      * Imports, defs, loops, with/try, etc.

    The `event` dict is merged read-only into the namespace (state wins on conflicts).
    """
    ns: Dict[str, Any] = {}
    state = state or {}
    if event:
        ns.update(event)
    ns.update(state)

    # Try expression first; on failure, fall back to statements
    try:
        result = _eval_expr(expr, ns)
        # Expressions do not mutate state; but if they referenced vars, nothing to sync.
        return result
    except EvalError:
        # Not a pure expression or failed gating; try as statements (assign/augassign)
        _exec_statements(expr, ns)
        # Sync all simple names back to state (we only allow simple names anyway)
        for k, v in ns.items():
            # Don’t copy SAFE_FUNCS or __builtins__/event-only keys by accident
            if k in _SAFE_FUNCS or k == "__builtins__":
                continue
            state[k] = v
        return None