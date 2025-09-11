# crapssim_control/cli.py
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from .controller import ControlStrategy
from .spec import validate_spec


def _load_spec(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _cmd_validate(args: argparse.Namespace) -> int:
    spec = _load_spec(args.spec)
    ok, errors = validate_spec(spec)
    if ok:
        print("OK: spec is valid.")
        return 0
    else:
        msg = "Failed validation: " + "; ".join(errors) if errors else "Failed validation."
        print(msg, file=sys.stderr)
        return 2


def _cmd_run(args: argparse.Namespace) -> int:
    # Defer import so that validate can run without engine installed
    try:
        import crapssim as cs  # type: ignore
    except Exception:
        print("Error: CrapsSim engine not available. Install with: pip install crapssim", file=sys.stderr)
        return 2

    spec = _load_spec(args.spec)
    ok, errs = validate_spec(spec)
    if not ok:
        print("Failed validation: " + "; ".join(errs), file=sys.stderr)
        return 2

    # Build engine table/player and run a tiny session
    table = cs.Table()
    player = cs.Player()
    table.add_player(player)

    strat = ControlStrategy(spec)

    # Minimal drive loop (shooters argument respected)
    shooters = int(getattr(args, "shooters", 1) or 1)
    for _ in range(shooters):
        table.new_shooter()
        # One comeout observation so strategies can stage
        strat.update_bets(table)
        # Throw a few rolls to smoke-test integration
        for _ in range(3):
            table.roll()
            strat.after_roll(table)
            strat.update_bets(table)

    # Exit cleanly
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="crapssim_control")
    sub = p.add_subparsers(dest="cmd", required=True)

    # validate
    pv = sub.add_parser("validate", help="Validate a strategy spec JSON")
    pv.add_argument("spec", help="Path to strategy spec JSON")
    pv.set_defaults(func=_cmd_validate)

    # run (engine smoke)
    pr = sub.add_parser("run", help="Run a short smoke test with CrapsSim engine")
    pr.add_argument("spec", help="Path to strategy spec JSON")
    pr.add_argument("--shooters", type=int, default=1, help="Number of shooters to simulate (default: 1)")
    pr.set_defaults(func=_cmd_run)

    return p


def main(argv: Any = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())