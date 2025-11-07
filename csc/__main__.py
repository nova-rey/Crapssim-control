"""Entry point shim for ``python -m csc``."""

from __future__ import annotations

import os
import sys

from crapssim_control.cli import main


def _enable_engine_soft_fail() -> None:
    """Allow the CLI to degrade gracefully when the CrapsSim engine is missing."""

    flag = os.environ.get("CSC_ENGINE_SOFT_FAIL")
    if flag is None:
        os.environ["CSC_ENGINE_SOFT_FAIL"] = "1"


if __name__ == "__main__":
    _enable_engine_soft_fail()
    # Friendly message for anyone invoking old entrypoints
    if "crapssim_control.cli" in sys.argv[0]:
        print("⚠️  Deprecated entrypoint. Use `python -m csc ...` instead.", file=sys.stderr)
    sys.exit(main())
