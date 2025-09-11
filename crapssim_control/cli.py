from __future__ import annotations

import argparse, json, sys
from typing import Any

try:
    import craps  # CrapsSim engine (pip install crapssim)
except Exception as e:
    craps = None

from .controller import ControlStrategy
from .telemetry import Telemetry


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="crapssim_control",
        description="Run a Craps strategy JSON with the Crapssim-Control runtime."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run a strategy JSON.")
    run.add_argument("spec", help="Path to strategy JSON.")
    run.add_argument("--shooters", type=int, default=10, help="Number of shooters to simulate.")
    run.add_argument("--level", type=int, default=None, help="Table minimum (e.g., 5/10/15/25). Overrides JSON.")
    run.add_argument("--bubble", type=int, choices=[0,1], default=None, help="Bubble craps (1) or not (0). Overrides JSON.")
    run.add_argument("--odds-policy", default=None,
                     help='Odds policy, e.g. "3-4-5x" or an integer (1x..20x). Overrides JSON.')
    run.add_argument("--telemetry", default=None, help="CSV path to write per-event telemetry (optional).")
    run.add_argument("--sample-every", type=int, default=None,
                     help="(reserved) Log every N rolls instead of all (not yet implemented).")

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(sys.argv[1:] if argv is None else argv)

    if ns.cmd == "run":
        if craps is None:
            print("Error: CrapsSim engine not available. Install with: pip install crapssim", file=sys.stderr)
            return 2

        # Load spec
        with open(ns.spec, "r", encoding="utf-8") as f:
            spec: dict[str, Any] = json.load(f)

        # Overrides from CLI
        table_cfg = spec.setdefault("table", {})
        if ns.level is not None:
            table_cfg["level"] = int(ns.level)
        if ns.bubble is not None:
            table_cfg["bubble"] = bool(ns.bubble)
        odds_policy = ns.odds_policy

        # Telemetry (optional)
        tele = Telemetry(ns.telemetry) if ns.telemetry else None
        try:
            strat = ControlStrategy(spec, telemetry=tele, odds_policy=odds_policy)

            # Build table
            level = int(table_cfg.get("level", 10))
            bubble = bool(table_cfg.get("bubble", False))
            table = getattr(craps, "Table", None)
            if table is None:
                print("Error: craps.Table not found in engine.", file=sys.stderr)
                return 2

            t = table(level=level, bubble=bubble)
            t.add_player(strat)

            # Run
            t.run(shooters=int(ns.shooters))

        finally:
            if tele is not None:
                tele.close()

        return 0

    print("Unknown command", file=sys.stderr)
    return 2