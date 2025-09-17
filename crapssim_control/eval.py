"""
eval.py -- Batch 12: Safe Expression Evaluator

Public API:
    evaluate(expr: str, state: dict | None = None, event: dict | None = None) -> Any
    eval_num(expr: str, state: dict | None = None, event: dict | None = None) -> float
    eval_bool(expr: str, state: dict | None = None, event: dict | None = None) -> bool

Features (whitelisted):
  - Literals: int, float, bool, str
  - Vars: names from `state` and `event`
  - Arithmetic: +, -, *, / (true division), unary -
  - Comparisons: ==, !=, <, <=, >, >= (chained ok)
  - Logic: and, or, not
  - Grouping: ( ... )
  - Python ternary:  a if cond else b
  - Helpers: min(x,y), max(x,y), abs(x), round(x[,nd]), floor(x), ceil(x)

Forbidden:
  - Attribute access (obj.attr), indexing/subscripts (a[0]), comprehensions, lambdas,
    function definitions, imports, names starting with '_' (dunder/privates), etc.

Errors:
  - Raises EvalError(message, expr, lineno, col_offset) with friendly context.
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


# -----------------------------
# Errors
# -----------------------------

@dataclass
class EvalError(Exception):
    message: str
    expr: str
    lineno: Optional[int] = None
    col_offset: Optional[int] = None

    def __str__(self) -> str:
        loc = ""
        if self.lineno is not None and self.col_offset is not None:
            loc = f" (at line {self.lineno}, col {self.col_offset})"
        return f"{self.message}{loc}\n  in: {self.expr}"


# -----------------------------
# Allowed helpers
# -----------------------------

_ALLOWED_FUNCS: Mapping[str, Any] = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
}


# -----------------------------
# Evaluator (AST walker)
# -----------------------------

class _Evaluator(ast.NodeVisitor):
    def __init__(self, expr: str, ctx: Mapping[str, Any]) -> None:
        self._expr = expr
        self._ctx = ctx

    # entry
    def evaluate(self, node: ast.AST) -> Any:
        try:
            return self.visit(node)
        except EvalError:
            raise
        except Exception as e:
            # Normalize any unexpected errors into EvalError
            line = getattr(node, "lineno", None)
            col = getattr(node, "col_offset", None)
            raise EvalError(f"Evaluation error: {e}", self._expr, line, col)

    # expression root
    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    # constants
    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, (int, float, bool, str)) or node.value is None:
            return node.value
        raise EvalError("Constant type not allowed", self._expr, node.lineno, node.col_offset)

    # names (variables)
    def visit_Name(self, node: ast.Name) -> Any:
        name = node.id
        if not name or name.startswith("_"):
            raise EvalError(f"Name '{name}' is not allowed", self._expr, node.lineno, node.col_offset)
        if name in _ALLOWED_FUNCS:
            # functions are only usable via Call; returning the function object is okay here
            return _ALLOWED_FUNCS[name]
        if name in self._ctx:
            v = self._ctx[name]
            # allow only simple JSON-ish values to flow through
            if isinstance(v, (int, float, bool, str)) or v is None:
                return v
            # Best effort: coerce to number if obvious
            raise EvalError(f"Variable '{name}' has unsupported type {type(v).__name__}", self._expr, node.lineno, node.col_offset)
        raise EvalError(f"Unknown variable '{name}'", self._expr, node.lineno, node.col_offset)

    # arithmetic
    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        raise EvalError(f"Operator '{type(op).__name__}' not allowed", self._expr, node.lineno, node.col_offset)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.Not):
            return not operand
        raise EvalError(f"Unary operator '{type(node.op).__name__}' not allowed", self._expr, node.lineno, node.col_offset)

    # boolean logic
    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if isinstance(node.op, ast.And):
            # short-circuit
            for v in node.values:
                if not self.visit(v):
                    return False
            return True
        if isinstance(node.op, ast.Or):
            for v in node.values:
                if self.visit(v):
                    return True
            return False
        raise EvalError(f"Boolean operator '{type(node.op).__name__}' not allowed", self._expr, node.lineno, node.col_offset)

    # comparisons (chained)
    def visit_Compare(self, node: ast.Compare) -> Any:
        left = self.visit(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self.visit(comp)
            ok: bool
            if isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            elif isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            else:
                raise EvalError(f"Comparison op '{type(op).__name__}' not allowed", self._expr, node.lineno, node.col_offset)
            if not ok:
                return False
            left = right
        return True

    # calls (helpers only)
    def visit_Call(self, node: ast.Call) -> Any:
        # Only simple Name() calls; no attribute or keyword calls to unknowns
        if not isinstance(node.func, ast.Name):
            raise EvalError("Only simple helper calls are allowed", self._expr, node.lineno, node.col_offset)
        fname = node.func.id
        if fname not in _ALLOWED_FUNCS:
            raise EvalError(f"Function '{fname}' is not allowed", self._expr, node.lineno, node.col_offset)
        fn = _ALLOWED_FUNCS[fname]
        # Evaluate args positionally; allow up to 2 args for helpers like min/max/round
        args = [self.visit(a) for a in node.args]
        # no **kwargs; allow simple keyword args for round(ndigits=) if provided
        kwargs = {}
        if node.keywords:
            for kw in node.keywords:
                if kw.arg not in ("ndigits",):  # only permit round(ndigits=)
                    raise EvalError("Keyword arguments not allowed", self._expr, node.lineno, node.col_offset)
                kwargs[kw.arg] = self.visit(kw.value)
            if fname != "round":
                raise EvalError("Keyword arguments only supported for round()", self._expr, node.lineno, node.col_offset)
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            raise EvalError(f"Error in {fname}(): {e}", self._expr, node.lineno, node.col_offset)

    # ternary: a if cond else b
    def visit_IfExp(self, node: ast.IfExp) -> Any:
        cond = self.visit(node.test)
        return self.visit(node.body) if cond else self.visit(node.orelse)

    # disallowed nodes
    def generic_visit(self, node: ast.AST) -> Any:
        DISALLOWED = (
            ast.Subscript, ast.Attribute, ast.List, ast.Tuple, ast.Dict, ast.Set,
            ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp,
            ast.Lambda, ast.If, ast.For, ast.While, ast.With, ast.Try,
            ast.Assign, ast.AugAssign, ast.AnnAssign, ast.NamedExpr,
            ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.ClassDef, ast.FunctionDef,
        )
        if isinstance(node, DISALLOWED):
            raise EvalError(f"Syntax not allowed: {type(node).__name__}", self._expr, getattr(node, "lineno", None), getattr(node, "col_offset", None))
        return super().generic_visit(node)


# -----------------------------
# Public functions
# -----------------------------

def _build_ctx(state: Optional[Dict[str, Any]], event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}
    if state:
        for k, v in state.items():
            if k and not str(k).startswith("_"):
                ctx[str(k)] = v
    if event:
        for k, v in event.items():
            if k and not str(k).startswith("_"):
                # event keys should not clobber state unless explicitly intended;
                # but for simplicity we let event overwrite (event data is "most recent").
                ctx[str(k)] = v
    # expose a read-only snapshot of helpers via names (already enforced in visit_Name/Call)
    for k in _ALLOWED_FUNCS:
        ctx.setdefault(k, _ALLOWED_FUNCS[k])
    return ctx


def evaluate(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> Any:
    """
    Evaluate a safe expression with variables from `state` and `event`.
    Raises EvalError on invalid syntax, unsafe constructs, or unknown variables.
    """
    if not isinstance(expr, str):
        raise EvalError("Expression must be a string", str(expr))
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as se:
        raise EvalError(f"Syntax error: {se.msg}", expr, se.lineno, se.offset)
    ev = _Evaluator(expr, _build_ctx(state, event))
    return ev.evaluate(tree)


def eval_num(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> float:
    v = evaluate(expr, state, event)
    if isinstance(v, bool):  # bool is a subclass of int; reject silently -> cast to float 0/1
        return float(v)
    try:
        return float(v)
    except Exception:
        raise EvalError(f"Expected numeric result, got {type(v).__name__}", expr)


def eval_bool(expr: str, state: Optional[Dict[str, Any]] = None, event: Optional[Dict[str, Any]] = None) -> bool:
    v = evaluate(expr, state, event)
    if isinstance(v, bool):
        return v
    # common coercions: nonzero numbers -> True; nonempty strings -> True
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "t", "1", "yes", "y"):
            return True
        if s in ("false", "f", "0", "no", "n"):
            return False
    raise EvalError(f"Expected boolean result, got {type(v).__name__}", expr)