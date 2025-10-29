"""Command line helper for parsing Strategy DSL sentences."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable, List

from .dsl_parser import DSLParseError, parse_file


def _load_source(argv: List[str]) -> str:
    if not argv:
        raise DSLParseError("No DSL sentence or file path provided")

    candidate = argv[0]
    path = Path(candidate)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return candidate


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print("Usage: csc parse-dsl <file_or_string>")
        return 1

    try:
        text = _load_source(args)
        rules = parse_file(text)
    except DSLParseError as exc:
        print(str(exc))
        return 2
    except OSError as exc:
        print(f"Failed to read input: {exc}")
        return 1

    print(json.dumps(rules, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
