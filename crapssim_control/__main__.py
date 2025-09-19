"""
Module entrypoint so tests can run:

  python -m crapssim_control validate path/to/spec.json

We keep this self-contained and defer other args to the CLI.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Dict, List

from .spec_validation import validate_spec
from . import cli as _cli  # for fallback to the run CLI


def _cmd_validate(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="crapssim_control validate",
        description="Validate a Craps strategy spec file (JSON).",
    )
    parser.add_argument("path", help="Path to the spec JSON file.")
    args = parser.parse_args(argv)

    p = pathlib.Path(args.path)
    try:
        with p.open("r", encoding="utf-8") as f:
            spec: Dict[str, Any] = json.load(f)
    except FileNotFoundError:
        print(f"failed validation: file not found: {p}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"failed validation: invalid JSON: {e}", file=sys.stderr)
        return 2

    errs = validate_spec(spec)
    if errs:
        # tests look for the phrase "failed validation" in stderr
        print("failed validation:", file=sys.stderr)
        for e in errs:
            print(f"- {e}", file=sys.stderr)
        return 2

    # Quiet success (stdout can be empty; tests only check return code)
    return 0


def main(argv: List[str] | None = None) -> int:  # pragma: no cover
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(
            "Usage:\n"
            "  python -m crapssim_control validate <spec.json>\n"
            "  # or use installed console script: crapssim-ctl --spec <spec.json>\n",
            file=sys.stderr,
        )
        return 2

    cmd = argv[0].lower()
    if cmd == "validate":
        return _cmd_validate(argv[1:])

    # Fallback: treat the rest as args for the run CLI
    return _cli.main(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())