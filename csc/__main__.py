"""Entry point shim for ``python -m csc``."""

import sys

from crapssim_control.cli import main


if __name__ == "__main__":
    # Friendly message for anyone invoking old entrypoints
    if "crapssim_control.cli" in sys.argv[0]:
        print("⚠️  Deprecated entrypoint. Use `python -m csc ...` instead.", file=sys.stderr)
    sys.exit(main())
