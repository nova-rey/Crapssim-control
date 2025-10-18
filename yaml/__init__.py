"""Minimal YAML loader fallback used when PyYAML is unavailable.

The implementation covers the small subset of YAML syntax exercised by the
project's fixtures: mappings, sequences, scalars, and basic nesting via
indentation.  It intentionally avoids advanced YAML features while presenting
an API-compatible ``safe_load`` entry point.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, List, Sequence, Tuple

__all__ = ["safe_load"]


@dataclass
class _Line:
    indent: int
    content: str


def _prepare_lines(text: str) -> List[_Line]:
    lines: List[_Line] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        in_single = False
        in_double = False
        cleaned_chars: List[str] = []
        for ch in stripped:
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            if ch == "#" and not in_single and not in_double:
                break
            cleaned_chars.append(ch)
        cleaned = "".join(cleaned_chars).strip()
        if not cleaned:
            continue
        indent = len(line) - len(line.lstrip(" "))
        lines.append(_Line(indent=indent, content=cleaned))
    return lines


class _Parser:
    def __init__(self, lines: Sequence[_Line]):
        self.lines = lines
        self.pos = 0

    def parse(self) -> Any:
        if not self.lines:
            return None
        base_indent = self.lines[0].indent
        return self._parse_block(base_indent)

    def _peek(self) -> Tuple[int, str] | None:
        if self.pos >= len(self.lines):
            return None
        line = self.lines[self.pos]
        return line.indent, line.content

    def _advance(self) -> Tuple[int, str]:
        line = self.lines[self.pos]
        self.pos += 1
        return line.indent, line.content

    def _parse_block(self, indent: int) -> Any:
        items: List[Any] = []
        mapping: dict[str, Any] = {}
        mode: str | None = None

        while True:
            peeked = self._peek()
            if peeked is None:
                break
            current_indent, content = peeked
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ValueError(f"Unexpected indentation at line {self.pos + 1}")

            if content.startswith("- ") or content == "-":
                if mode == "mapping":
                    raise ValueError("Cannot mix mapping and sequence at same level")
                mode = "sequence"
                items.append(self._parse_list_item(indent))
            else:
                if mode == "sequence":
                    raise ValueError("Cannot mix mapping and sequence at same level")
                if ":" not in content:
                    _, scalar_content = self._advance()
                    return self._parse_scalar(scalar_content)
                mode = "mapping"
                key, value = self._parse_mapping_entry(indent)
                mapping[key] = value

        if mode == "sequence":
            return items
        if mode == "mapping":
            return mapping
        return None

    def _parse_list_item(self, indent: int) -> Any:
        _, content = self._advance()
        remainder = content[1:].strip()
        if not remainder:
            return self._parse_nested(indent)
        if remainder.startswith("- "):
            self.pos -= 1
            return self._parse_nested(indent)
        if ":" in remainder and not remainder.endswith(":"):
            key, value = remainder.split(":", 1)
            key = key.strip()
            value = value.strip()
            item: dict[str, Any] = {key: self._parse_scalar(value)}
            if self._peek() and self._peek()[0] > indent:
                nested = self._parse_block(self._peek()[0])
                if isinstance(nested, dict):
                    item.update(nested)
                else:
                    item[key] = nested
            return item
        if remainder.endswith(":"):
            key = remainder[:-1].strip()
            value = self._parse_nested(indent)
            return {key: value}
        return self._parse_scalar(remainder)

    def _parse_mapping_entry(self, indent: int) -> Tuple[str, Any]:
        _, content = self._advance()
        key, remainder = content.split(":", 1)
        key = key.strip()
        remainder = remainder.strip()
        if remainder:
            return key, self._parse_scalar(remainder)
        return key, self._parse_nested(indent)

    def _parse_nested(self, parent_indent: int) -> Any:
        peeked = self._peek()
        if peeked is None or peeked[0] <= parent_indent:
            return None
        nested_indent = peeked[0]
        return self._parse_block(nested_indent)

    def _parse_scalar(self, token: str) -> Any:
        lowered = token.lower()
        if lowered in {"null", "none", "~"}:
            return None
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            if token.startswith("0") and token != "0" and not token.startswith("0."):
                raise ValueError
            return int(token)
        except ValueError:
            try:
                return float(token)
            except ValueError:
                pass
        try:
            return ast.literal_eval(token)
        except Exception:
            return token


def safe_load(stream: Any) -> Any:
    if hasattr(stream, "read"):
        text = stream.read()
    else:
        text = str(stream)
    lines = _prepare_lines(text)
    parser = _Parser(lines)
    return parser.parse()
