"""Strategy DSL sentence parser.

This module converts human readable WHEN/THEN sentences into
normalized rule dictionaries. The grammar is intentionally small
and only validates surface structure; deeper expression evaluation
will be introduced in later checkpoints.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from .dsl_eval import compile_expr

__all__ = [
    "DSLParseError",
    "parse_sentence",
    "parse_file",
    "compile_rules",
]

TOKEN_RE = re.compile(
    r"\s*(?:(AND|OR)|([<>!=]=|[<>=])|(\()|(\))|([A-Za-z0-9_.]+)|(\".*?\")|(\'.*?\'))",
    re.IGNORECASE,
)


class DSLParseError(Exception):
    """Raised when the DSL parser encounters invalid syntax."""

    def __init__(self, message: str, *, line: int = 1, col: int = 0) -> None:
        self.message = message
        self.line = line
        self.col = col
        super().__init__(f"DSL parse error at line {line}, col {col}: {message}")


def _tokenize(expr: str) -> List[str]:
    """Tokenize a condition expression for basic validation."""

    tokens: List[str] = []
    pos = 0
    length = len(expr)

    while pos < length:
        match = TOKEN_RE.match(expr, pos)
        if not match:
            raise DSLParseError(f"Unexpected character '{expr[pos]}'", col=pos)
        token = next((group for group in match.groups() if group), None)
        if token is not None:
            tokens.append(token)
        pos = match.end()
    return tokens


def _parse_args(arg_str: str) -> Dict[str, Any]:
    if not arg_str:
        return {}

    args: Dict[str, Any] = {}
    for segment in arg_str.split(","):
        piece = segment.strip()
        if not piece:
            continue
        if "=" in piece:
            key, value = piece.split("=", 1)
            args[key.strip()] = value.strip().strip('\"\'')
        else:
            args[piece] = True
    return args


def parse_sentence(sentence: str) -> Dict[str, Any]:
    """Parse a DSL sentence into a normalized rule dictionary.

    Sentences must follow the minimal grammar:

        WHEN <condition> THEN <verb>(<args>)

    Args are optional and may be expressed as ``key=value`` pairs or
    bare identifiers (treated as boolean flags). The parser performs
    surface validation only; expression evaluation is deferred.
    """

    if not sentence or not sentence.strip():
        raise DSLParseError("Empty sentence")

    parts = re.split(r"\bTHEN\b", sentence, flags=re.IGNORECASE)
    if len(parts) != 2:
        raise DSLParseError("Missing THEN in sentence")

    cond_part, action_part = parts
    cond_match = re.search(r"\bWHEN\b", cond_part, flags=re.IGNORECASE)
    if not cond_match:
        raise DSLParseError("Missing WHEN in sentence")

    condition = cond_part[cond_match.end():].strip()
    if not condition:
        raise DSLParseError("Missing condition expression after WHEN")

    # Basic token validation to surface unexpected characters early.
    _tokenize(condition)

    action_text = action_part.strip()
    action_match = re.match(
        r"^([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*$",
        action_text,
        flags=re.DOTALL,
    )
    if not action_match:
        raise DSLParseError("Malformed THEN clause; expected verb(args)")

    verb = action_match.group(1)
    arg_str = action_match.group(2).strip()
    args = _parse_args(arg_str)

    return {
        "id": f"rule_{verb}",
        "when": condition,
        "then": {"verb": verb, "args": args},
        "scope": "roll",
        "cooldown": 0,
        "once": False,
    }


def parse_file(text: str) -> List[Dict[str, Any]]:
    """Parse a DSL file containing one sentence per non-empty line."""

    rules: List[Dict[str, Any]] = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        sentence = raw_line.strip()
        if not sentence or sentence.startswith("#"):
            continue
        try:
            rule = parse_sentence(sentence)
        except DSLParseError as err:
            raise DSLParseError(err.message, line=line_no, col=err.col) from err
        rules.append(rule)
    return rules


def compile_rules(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach compiled '_compiled' AST to each rule's WHEN string."""

    compiled: List[Dict[str, Any]] = []
    for rule in rules:
        rule_copy = dict(rule)
        when_expr = rule_copy.get("when", "")
        rule_copy["_compiled"] = compile_expr(when_expr)
        compiled.append(rule_copy)
    return compiled
