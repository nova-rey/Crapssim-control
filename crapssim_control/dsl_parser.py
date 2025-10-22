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

    def __init__(self, message: str, line: int = 1, col: int = 1, snippet: str = "") -> None:
        self.detail = message
        self.line = int(line)
        self.col = int(col)
        self.snippet = snippet
        caret = ""
        if snippet:
            caret = " " * (max(0, self.col - 1)) + "^"
        loc = f"line {self.line}, col {self.col}"
        full_msg = f"DSL parse error at {loc}: {message}"
        if snippet:
            full_msg += f"\n  {snippet}\n  {caret}"
        super().__init__(full_msg)
        # Provide compatibility attribute used by older call sites
        self.message = full_msg


def _line_col(source: str, offset: int) -> tuple[int, int, str]:
    """Return (line, col, snippet) from a 0-based offset into ``source``."""

    lines = source.splitlines(True)
    total = 0
    for idx, line in enumerate(lines, start=1):
        next_total = total + len(line)
        if offset < next_total:
            col = offset - total + 1
            return idx, col, line.rstrip("\n\r")
        total = next_total
    if lines:
        snippet = lines[-1].rstrip("\n\r")
        return len(lines), len(snippet) + 1, snippet
    return 1, 1, ""


def _tokenize(expr: str, *, source: str = "", base_offset: int = 0) -> List[str]:
    """Tokenize a condition expression for basic validation."""

    tokens: List[str] = []
    pos = 0
    length = len(expr)

    while pos < length:
        match = TOKEN_RE.match(expr, pos)
        if not match:
            offset = base_offset + pos
            if source:
                line, col, snippet = _line_col(source, offset)
                raise DSLParseError(
                    f"Unexpected character '{expr[pos]}' in condition",
                    line=line,
                    col=col,
                    snippet=snippet,
                )
            raise DSLParseError(
                f"Unexpected character '{expr[pos]}' in condition",
                line=1,
                col=pos + 1,
                snippet=expr,
            )
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

    src = sentence or ""
    if not src.strip():
        raise DSLParseError("Empty sentence", line=1, col=1, snippet=src)

    then_match = re.search(r"\bTHEN\b", src, flags=re.IGNORECASE)
    if not then_match:
        idx = len(src)
        upper_idx = src.upper().find("THEN")
        if upper_idx >= 0:
            idx = upper_idx
        line, col, snippet = _line_col(src, idx)
        raise DSLParseError("Missing THEN in sentence", line=line, col=col, snippet=snippet)

    cond_part = src[: then_match.start()]
    action_part = src[then_match.end() :]

    cond_match = re.search(r"\bWHEN\b", cond_part, flags=re.IGNORECASE)
    if not cond_match:
        upper_idx = src.upper().find("WHEN")
        idx = upper_idx if upper_idx >= 0 else 0
        line, col, snippet = _line_col(src, idx)
        raise DSLParseError("Missing WHEN in sentence", line=line, col=col, snippet=snippet)

    condition_raw = cond_part[cond_match.end() :]
    leading_ws = len(condition_raw) - len(condition_raw.lstrip())
    condition = condition_raw.strip()
    cond_start_offset = cond_match.end() + max(0, leading_ws)
    if not condition:
        line, col, snippet = _line_col(src, cond_start_offset)
        raise DSLParseError(
            "Missing condition expression after WHEN",
            line=line,
            col=col,
            snippet=snippet,
        )

    # Basic token validation to surface unexpected characters early.
    _tokenize(condition, source=src, base_offset=cond_start_offset)

    action_raw = action_part
    action_text = action_raw.strip()
    action_match = re.match(
        r"^([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*$",
        action_text,
        flags=re.DOTALL,
    )
    if not action_match:
        action_offset = then_match.end() + (len(action_raw) - len(action_raw.lstrip()))
        line, col, snippet = _line_col(src, action_offset)
        raise DSLParseError(
            "Malformed THEN clause; expected verb(args)",
            line=line,
            col=col,
            snippet=snippet,
        )

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
        line_text = raw_line.rstrip("\n\r")
        if not line_text.strip() or line_text.lstrip().startswith("#"):
            continue
        try:
            rule = parse_sentence(line_text)
        except DSLParseError as err:
            snippet = err.snippet or line_text
            line = line_no + (err.line - 1)
            raise DSLParseError(err.detail, line=line, col=err.col, snippet=snippet) from err
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
