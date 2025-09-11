# crapssim_control/cli.py
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .controller import ControlStrategy
from .spec import validate_spec
from .telemetry import Telemetry
from .engine_adapter import EngineAdapter


def _load_spec(path: str) -> Dict[str, Any]:
    p = Path(path)
    with p.open("r") as f:
        data = json.load(f)
    validate_spec(data)
    return data


def _resolve_odds_policy(spec: Dict[str, Any], cli_value: Optional[str]) -> Optional[str]:
    if cli_value is not None:
        return cli_value
    return spec.get("table", {}).get("odds_policy")


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        _ = _load_spec(args.spec)
        print("OK: spec is valid.")
        return 0
    except Exception as e:
        print(f"Invalid: {e}", file=sys.stderr)
        return 2


def cmd_run(args: argparse.Namespace) -> int:
    # Try to import the engine lazily so the validate command remains usable without CrapsSim.
    try:
        from crapssim import Table, Player  # type: ignore
    except Exception:
        print("Error: CrapsSim engine not available. Install with: pip install crapssim", file=sys.stderr)
        return 2

    try:
        spec = _load_spec(args.spec)
    except Exception as e:
        print(f"Invalid spec: {e}", file=sys.stderr)
        return 2

    odds_policy = _resolve_odds_policy(spec, args.odds_policy)
    telemetry = Telemetry(enabled=not args.no_telemetry, csv_path=args.telemetry_csv)

    # Build strategy
    strategy = ControlStrategy(spec, telemetry=telemetry, odds_policy=odds_policy)

    # Build engine objects
    table = Table()
    player = Player(bankroll=args.bankroll)
    table.add_player(player)

    # Run via adapter
    adapter = EngineAdapter(table, player, strategy)
    shooters = args.shooters if args.shooters > 0 else 1
    adapter.play(shooters=shooters)

    # Flush telemetry (close file) if needed
    telemetry.close()
    print("Run complete.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="crapssim_control")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="Validate a strategy spec JSON.")
    v.add_argument("spec", help="Path to JSON file")
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("run", help="Run a strategy spec JSON via CrapsSim.")
    r.add_argument("spec", help="Path to JSON file")
    r.add_argument("--shooters", type=int, default=10, help="Number of shooters to simulate (default: 10)")
    r.add_argument("--bankroll", type=float, default=1000.0, help="Initial bankroll for the player (default: 1000)")
    r.add_argument("--odds-policy", choices=["3-4-5x", "2x", "5x", "none"], default=None,
                   help="Override table.odds_policy for this run.")
    r.add_argument("--no-telemetry", action="store_true", help="Disable telemetry CSV output")
    r.add_argument("--telemetry-csv", default=None, help="Path to write telemetry CSV (default: strategy-name.csv)")
    r.set_defaults(func=cmd_run)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())