# crapssim_control/eval.py
from __future__ import annotations

import ast
import math
from typing import Any, Dict, Optional

__all__ = [
    "EvalError",
    "evaluate",
    "safe_eval",
    "eval_num",
    "eval_bool",
]

class EvalError(Exception):
    """
    Uniform error for the safe evaluator.
    We keep messages human-readable since tests assert on them.
    """

    def __init__(self, message: str, expr: str, lineno: Optional[int] = None, col: Optional[int] = None):
        self.message = message
        self.expr = expr
        self.lineno = lineno
        self.col = col
        pretty_loc = ""
        if lineno is not None and col is not None:
            pretty_loc = f" (at line {lineno}, col {col})"
        tail = f"\n  in: {expr}" if expr else ""
        super().__init__(f"{message}{pretty_loc}{tail}")


# ---- Allowed helpers ---------------------------------------------------------

SAFE_FUNCS: Dict[str, Any] = {
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "min": min,
    "max": max,
    "abs": abs,
    "int": int,
    "float": float,
    # allow rules that include "apply_template('Aggressive')" as a harmless action
    "apply_template": lambda *_, **__: None,
}

# Expression nodes allowed (NO subscripts/slices; calls allowed but gated)
_ALLOWED_EXPR_NODES = {
    ast.Expression, ast.UnaryOp, ast.BinOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Name, ast.Load, ast.Constant, ast.Dict, ast.List, ast.Tuple,
    ast.Attribute, ast.Call,  # Call allowed but validated by _assert_calls_allowed
    ast.And, ast.Or, ast.Not,
    ast.USub, ast.UAdd,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
}

# Statement nodes allowed for simple assignments/aug-assign (NO subscripts/calls except whitelisted)
_ALLOWED_STMT_NODES = {
    ast.Module, ast.Assign, ast.AugAssign, ast.Store, ast.Name, ast.Expr,
    ast.UnaryOp, ast.BinOp, ast.BoolOp, ast.Compare, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd,
    ast.IfExp, ast.Tuple, ast.List, ast.Dict,
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

def _assert_no_subscripts(node: ast.AST) -> None:
    for child in ast.walk(node):
        if isinstance(child, (ast.Subscript, ast.Slice)):
            raise EvalError("Disallowed syntax: Subscript", "", getattr(child, "lineno", None), getattr(child, "col_offset", None))

def _assert_calls_allowed(node: ast.AST) -> None:
    """
    Only allow Call nodes when the callable resolves to a Name present in SAFE_FUNCS.
    Attribute-call patterns like x.y() are rejected with a "not allowed" message.
    """
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            # case: Name(...) -- allow only if name in SAFE_FUNCS
            if isinstance(child.func, ast.Name):
                fn = child.func.id
                if fn not in SAFE_FUNCS:
                    # phrase must include "not allowed" per tests
                    raise EvalError(f"Function '{fn}' not allowed", "", getattr(child, "lineno", None), getattr(child, "col_offset", None))
            else:
                # Attribute / Subscript callee etc. -- reject
                raise EvalError("Function call not allowed", "", getattr(child, "lineno", None), getattr(child, "col_offset", None))


# ---- Public API --------------------------------------------------------------

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
    _assert_no_subscripts(tree)
    _assert_calls_allowed(tree)

    try:
        code = compile(tree, "<safe_eval>", "eval")
        # expose only whitelisted builtins
        result = eval(code, {"__builtins__": {}, **SAFE_FUNCS}, local_ns)
        # propagate any container mutations back
        if isinstance(state, dict):
            state.clear()
            state.update(local_ns)
        return result
    except NameError as ne:
        # Unknown variable -- tests expect "Unknown variable '<name>'"
        name = getattr(ne, "name", None)
        if name:
            raise EvalError(f"Unknown variable '{name}'", expr)
        raise EvalError(f"Unknown variable", expr)
    except EvalError:
        raise
    except Exception as ex:
        # generic runtime failure
        raise EvalError(f"Runtime error: {ex}", expr)


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
        _assert_no_subscripts(tree)
        _assert_calls_allowed(tree)
        code = compile(tree, "<eval>", "eval")
        result = eval(code, {"__builtins__": {}, **SAFE_FUNCS}, local_ns)
        # push back locals only for simple expressions that may mutate containers
        if isinstance(state, dict):
            state.clear()
            state.update(local_ns)
        return result
    except SyntaxError:
        pass  # fall through to exec
    except NameError as ne:
        name = getattr(ne, "name", None)
        if name:
            raise EvalError(f"Unknown variable '{name}'", expr)
        raise EvalError("Unknown variable", expr)
    except EvalError:
        raise
    except Exception as ex:
        # if the error stemmed from an attempt to call a non-whitelisted function, surface "not allowed"
        msg = str(ex)
        if "is not defined" in msg:
            raise EvalError("Function call not allowed", expr)
        raise EvalError(f"Runtime error: {ex}", expr)

    # 2) Fallback: simple statement(s) exec -- allow Assign/AugAssign only
    try:
        tree = ast.parse(expr, mode="exec")
    except SyntaxError as se:
        raise EvalError(f"Syntax error: {se.msg}", expr, se.lineno, se.offset)

    _assert_allowed(tree, _ALLOWED_STMT_NODES)
    _assert_no_subscripts(tree)

    # Only allow bare Assign/AugAssign and simple Expr of whitelisted calls (e.g. apply_template(...))
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            _assert_calls_allowed(node)
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            # LHS must be plain Name
            targets = [node.target] if isinstance(node, ast.AugAssign) else node.targets
            for t in targets:
                if not isinstance(t, ast.Name):
                    raise EvalError("Disallowed assignment target", expr, getattr(t, "lineno", None), getattr(t, "col_offset", None))
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            pass
        else:
            # reject any other statement kinds
            raise EvalError(f"Disallowed syntax: {type(node).__name__}", expr, getattr(node, "lineno", None), getattr(node, "col_offset", None))

    try:
        code = compile(tree, "<exec>", "exec")
        exec(code, {"__builtins__": {}, **SAFE_FUNCS}, local_ns)
        if isinstance(state, dict):
            state.clear()
            state.update(local_ns)
        return None
    except NameError as ne:
        name = getattr(ne, "name", None)
        if name:
            raise EvalError(f"Unknown variable '{name}'", expr)
        raise EvalError("Unknown variable", expr)
    except EvalError:
        raise
    except Exception as ex:
        raise EvalError(f"Runtime error: {ex}", expr)


def eval_num(expr: Any, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> float:
    """
    Evaluate to a number using safe_eval/evaluate semantics.
    """
    if isinstance(expr, (int, float)):
        return float(expr)
    val = safe_eval(str(expr), _merged_state(state, event))
    try:
        return float(val)
    except Exception:
        raise EvalError("Not a number", str(expr))


def eval_bool(expr: Any, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> bool:
    """
    Evaluate to a boolean with helpful coercions:
      - numbers: 0 -> False, non-zero -> True
      - strings: 'true','yes','on' -> True ; 'false','no','off' -> False
    """
    if isinstance(expr, bool):
        return expr
    if isinstance(expr, (int, float)):
        return bool(expr)
    if isinstance(expr, str):
        s = expr.strip()
        # if this is a quoted literal like "'no'" tests pass the string as an expression
        if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
            lit = s[1:-1].strip().lower()
            if lit in {"false", "no", "off"}:
                return False
            if lit in {"true", "yes", "on"}:
                return True
        # otherwise evaluate the expression
        val = safe_eval(expr, _merged_state(state, event))
    else:
        val = safe_eval(str(expr), _merged_state(state, event))

    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        lit = val.strip().lower()
        if lit in {"false", "no", "off", ""}:
            return False
        if lit in {"true", "yes", "on"}:
            return True
    return bool(val)


def _merged_state(state: Optional[Dict[str, Any]], event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Event overlay takes precedence when both provide the same key (as tests expect)."""
    base = dict(state or {})
    if event:
        base.update(event)
    return base