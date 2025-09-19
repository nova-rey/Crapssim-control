#!/usr/bin/env python3
"""
Lightweight pre-release checker:
- Ensures version is set
- Ensures README/SPEC exist
- Quick import of CLI entrypoint

Usage:
  python scripts/release_check.py
"""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
pkg_init = root / "crapssim_control" / "__init__.py"
readme = root / "README.md"
specmd = root / "SPEC.md"

errors = []

# Version check
try:
    ns = {}
    exec(pkg_init.read_text(encoding="utf-8"), ns, ns)
    version = ns.get("__version__")
    if not version:
        errors.append("Missing __version__ in crapssim_control/__init__.py")
except Exception as e:
    errors.append(f"Could not read __init__.py: {e}")

# Docs exist
if not readme.exists():
    errors.append("Missing README.md")
if not specmd.exists():
    errors.append("Missing SPEC.md")

# CLI import check
try:
    __import__("crapssim_control.cli")
except Exception as e:
    errors.append(f"CLI import failed: {e}")

if errors:
    print("release_check: FAILED")
    for e in errors:
        print(f"- {e}")
    sys.exit(2)

print("release_check: OK")