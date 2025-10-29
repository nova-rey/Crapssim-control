# scripts/validate_spec.py
"""
Convenience wrapper to validate a spec file from the command line.

Usage:
    python scripts/validate_spec.py path/to/spec.json
"""
import json
import sys
from pathlib import Path

from crapssim_control.spec_validation import validate_spec


def main(argv):
    if len(argv) != 2:
        print("Usage: python scripts/validate_spec.py <path-to-spec.json>")
        return 2
    p = Path(argv[1])
    if not p.exists():
        print(f"File not found: {p}")
        return 2
    try:
        spec = json.loads(p.read_text())
    except Exception as e:
        print(f"Failed to parse JSON: {e}")
        return 2

    errs = validate_spec(spec)
    if errs:
        print("Invalid spec:")
        for e in errs:
            print(f"  - {e}")
        return 1

    print("Spec is valid ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
