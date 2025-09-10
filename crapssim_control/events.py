# crapssim_control/eval.py
import ast, operator, math

_ALLOWED_FUNCS = {
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
}

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

_COMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

_BOOL_OPS = {
    ast.And: all,
    ast.Or: any,
}

def safe_eval(expr: str, names: dict) -> int | float | bool:
    """
    Evaluate a tiny expression with a strict whitelist.

    Allowed:
      - literals (ints/floats/bools)
      - provided variable names (from 'names' dict)
      - arithmetic: + - * / // %
      - comparisons: == != < <= > >=
      - boolean: and/or/not
      - funcs: min, max, abs, round, floor, ceil
    """
    expr = str(expr).strip()  # tolerate leading/trailing whitespace in SPEC strings
    node = ast.parse(expr, mode="eval").body
    return _eval(node, names)

def _eval(node, names):
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in names:
            return names[node.id]
        if node.id in _ALLOWED_FUNCS:
            return _ALLOWED_FUNCS[node.id]
        raise NameError(f"name '{node.id}' not allowed")

    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if not op:
            raise TypeError("operator not allowed")
        return op(_eval(node.left, names), _eval(node.right, names))

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
        val = _eval(node.operand, names)
        if isinstance(node.op, ast.UAdd):
            return +val
        if isinstance(node.op, ast.USub):
            return -val
        if isinstance(node.op, ast.Not):
            return not val

    if isinstance(node, ast.Call):
        func = _eval(node.func, names)
        args = [_eval(a, names) for a in node.args]
        if func in _ALLOWED_FUNCS.values():
            return func(*args)
        raise TypeError("function not allowed")

    if isinstance(node, ast.BoolOp):
        opf = _BOOL_OPS.get(type(node.op))
        if not opf:
            raise TypeError("bool op not allowed")
        vals = [_eval(v, names) for v in node.values]
        return opf(vals)

    if isinstance(node, ast.Compare):
        left = _eval(node.left, names)
        result = True
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, names)
            if not _COMP_OPS[type(op)](left, right):
                result = False
                break
            left = right
        return result

    raise TypeError("expression not allowed")