from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Tuple, Union

__all__ = [
    "ExpressionError",
    "compile_expr",
    "evaluate_condition",
]


class ExpressionError(Exception):
    """Raised for invalid DSL expressions."""


Token = Tuple[str, str]


# --------- Tokenizer ---------
_TOKEN_SPEC: Tuple[Tuple[str, str], ...] = (
    ("WS", r"[ \t\n\r]+"),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("AND", r"(?i:\bAND\b)"),
    ("OR", r"(?i:\bOR\b)"),
    ("NOT", r"(?i:\bNOT\b)"),
    ("OP", r"(<=|>=|!=|==|<|>)"),
    ("BOOL", r"(?i:\bTRUE\b|\bFALSE\b)"),
    ("NUM", r"\b\d+(?:\.\d+)?\b"),
    ("DOTTED", r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*"),
    ("STRING", r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\""),
)
_MASTER_RE = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in _TOKEN_SPEC))
_STRING_ESCAPE_RE = re.compile(r"\\(.)")
_ESCAPE_MAP = {"n": "\n", "r": "\r", "t": "\t", "'": "'", '"': '"', "\\": "\\"}
_INVALID_SEGMENT_RE = re.compile(r"__")


def _tokenize(expr: str) -> List[Token]:
    tokens: List[Token] = []
    pos = 0
    length = len(expr)
    while pos < length:
        match = _MASTER_RE.match(expr, pos)
        if not match:
            raise ExpressionError(f"Unexpected character at position {pos}: {expr[pos]!r}")
        token_type = match.lastgroup
        token_value = match.group()
        pos = match.end()
        if token_type == "WS":
            continue
        if token_type in {"AND", "OR", "NOT", "BOOL"}:
            token_value = token_value.upper()
        if token_type == "DOTTED":
            segments = token_value.split(".")
            if any(_INVALID_SEGMENT_RE.search(seg) for seg in segments):
                raise ExpressionError("Identifiers must not contain double underscores")
        tokens.append((token_type, token_value))
    return tokens


# --------- AST Nodes ---------
def _node_var(name: str) -> Dict[str, Any]:
    return {"type": "var", "name": name}


def _node_bool(val: bool) -> Dict[str, Any]:
    return {"type": "bool", "value": val}


def _node_num(val: Union[int, float]) -> Dict[str, Any]:
    return {"type": "num", "value": val}


def _node_str(val: str) -> Dict[str, Any]:
    return {"type": "str", "value": val}


def _node_not(child: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "not", "child": child}


def _node_bin(op: str, left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "bin", "op": op, "left": left, "right": right}


def _node_cmp(op: str, left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "cmp", "op": op, "left": left, "right": right}


# --------- Recursive-descent Parser ---------


class _Parser:
    def __init__(self, tokens: List[Token]):
        self._tokens = tokens
        self._index = 0

    def _peek(self) -> Union[Token, None]:
        if self._index < len(self._tokens):
            return self._tokens[self._index]
        return None

    def _accept(self, *types: str) -> Union[Token, None]:
        token = self._peek()
        if token and token[0] in types:
            self._index += 1
            return token
        return None

    def _expect(self, *types: str) -> Token:
        token = self._accept(*types)
        if not token:
            expected = " or ".join(types)
            got = self._peek()[0] if self._peek() else "EOF"
            raise ExpressionError(f"Expected {expected}, got {got}")
        return token

    def parse(self) -> Dict[str, Any]:
        node = self._parse_or()
        if self._peek() is not None:
            raise ExpressionError("Trailing tokens after expression")
        return node

    def _parse_or(self) -> Dict[str, Any]:
        node = self._parse_and()
        while self._accept("OR"):
            right = self._parse_and()
            node = _node_bin("OR", node, right)
        return node

    def _parse_and(self) -> Dict[str, Any]:
        node = self._parse_not()
        while self._accept("AND"):
            right = self._parse_not()
            node = _node_bin("AND", node, right)
        return node

    def _parse_not(self) -> Dict[str, Any]:
        negate = False
        while self._accept("NOT"):
            negate = not negate
        node = self._parse_cmp()
        return _node_not(node) if negate else node

    def _parse_cmp(self) -> Dict[str, Any]:
        left = self._parse_term()
        op_token = self._accept("OP")
        if op_token:
            right = self._parse_term()
            return _node_cmp(op_token[1], left, right)
        return left

    def _parse_term(self) -> Dict[str, Any]:
        if self._accept("LPAREN"):
            expr = self._parse_or()
            self._expect("RPAREN")
            return expr
        token = self._accept("BOOL", "NUM", "STRING", "DOTTED")
        if not token:
            raise ExpressionError("Expected BOOL, NUM, STRING, identifier, or '(' ")
        token_type, token_value = token
        if token_type == "BOOL":
            return _node_bool(token_value == "TRUE")
        if token_type == "NUM":
            if "." in token_value:
                return _node_num(float(token_value))
            return _node_num(int(token_value))
        if token_type == "STRING":
            inner = token_value[1:-1]
            inner = _STRING_ESCAPE_RE.sub(lambda m: _ESCAPE_MAP.get(m.group(1), m.group(1)), inner)
            return _node_str(inner)
        return _node_var(token_value)


# --------- Snapshot helpers ---------


def _path_get(snapshot: Dict[str, Any], dotted: str) -> Any:
    current: Any = snapshot
    for segment in dotted.split("."):
        if isinstance(current, dict):
            if segment in current:
                current = current[segment]
                continue
            if segment.isdigit():
                key = int(segment)
                if key in current:
                    current = current[key]
                    continue
        raise ExpressionError(f"Unknown snapshot path '{dotted}'")
    return current


def _truthy(value: Any) -> bool:
    return bool(value)


# --------- Evaluator ---------


def _eval_node(node: Dict[str, Any], snapshot: Dict[str, Any]) -> Any:
    node_type = node["type"]
    if node_type in {"bool", "num", "str"}:
        return node["value"]
    if node_type == "var":
        value = _path_get(snapshot, node["name"])
        return _truthy(value)
    if node_type == "not":
        return not _eval_node(node["child"], snapshot)
    if node_type == "bin":
        left = _eval_node(node["left"], snapshot)
        right = _eval_node(node["right"], snapshot)
        if node["op"] == "AND":
            return bool(left) and bool(right)
        if node["op"] == "OR":
            return bool(left) or bool(right)
        raise ExpressionError(f"Unknown boolean operator '{node['op']}'")
    if node_type == "cmp":
        left_val = _eval_value(node["left"], snapshot)
        right_val = _eval_value(node["right"], snapshot)
        op = node["op"]
        try:
            if op == "<":
                return left_val < right_val
            if op == ">":
                return left_val > right_val
            if op == "<=":
                return left_val <= right_val
            if op == ">=":
                return left_val >= right_val
            if op == "==":
                return left_val == right_val
            if op == "!=":
                return left_val != right_val
        except TypeError:
            return False
        raise ExpressionError(f"Unknown comparison operator '{op}'")
    raise ExpressionError(f"Unknown node type '{node_type}'")


def _eval_value(node: Dict[str, Any], snapshot: Dict[str, Any]) -> Any:
    node_type = node["type"]
    if node_type in {"bool", "num", "str"}:
        return node["value"]
    if node_type == "var":
        return _path_get(snapshot, node["name"])
    return _eval_node(node, snapshot)


# --------- Public API ---------
_COMPILE_CACHE: Dict[str, Dict[str, Any]] = {}


def compile_expr(expr: str) -> Dict[str, Any]:
    key = (expr or "").strip()
    if not key:
        return _node_bool(True)
    cached = _COMPILE_CACHE.get(key)
    if cached is not None:
        return copy.deepcopy(cached)
    tokens = _tokenize(key)
    ast = _Parser(tokens).parse()
    _COMPILE_CACHE[key] = ast
    return copy.deepcopy(ast)


def evaluate_condition(expr: str, snapshot: Dict[str, Any]) -> bool:
    ast = compile_expr(expr)
    return bool(_eval_node(ast, snapshot))
