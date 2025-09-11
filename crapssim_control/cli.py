# crapssim_control/cli.py
from __future__ import annotations

import argparse, json, sys
from typing import Any

try:
    import craps  # CrapsSim engine (pip install crapssim)
except Exception:
    craps = None

from .controller import ControlStrategy
from .telemetry import Telemetry
from .spec import validate_spec


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="crapssim_control",
        description="Run or validate CrapsSim Control strategy JSON."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # run
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

    # validate
    val = sub.add_parser("validate", help="Validate a strategy JSON (structural checks).")
    val.add_argument("spec", help="Path to strategy JSON.")
    val.add_argument("--strict", action="store_true",
                     help="Exit non-zero on warnings (future use).")

    return p.parse_args(argv)


def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _cmd_validate(path: str, strict: bool = False) -> int:
    try:
        data = _load_json(path)
    except Exception as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        return 2

    ok, errors = validate_spec(data)
    if ok:
        print(f"OK: {path} is a valid CrapsSim Control spec.")
        return 0
    else:
        print(f"ERROR: {path} failed validation with {len(errors)} error(s):", file=sys.stderr)
        for i, msg in enumerate(errors, 1):
            print(f"  {i}. {msg}", file=sys.stderr)
        return 1


def _cmd_run(ns: argparse.Namespace) -> int:
    if craps is None:
        print("Error: CrapsSim engine not available. Install with: pip install crapssim", file=sys.stderr)
        return 2

    # Load spec
    try:
        spec: dict[str, Any] = _load_json(ns.spec)
    except Exception as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        return 2

    # Validate (non-fatal for now, just print warnings)
    ok, errs = validate_spec(spec)
    if not ok:
        print(f"WARNING: spec has {len(errs)} validation error(s). Continuing anyway:", file=sys.stderr)
        for m in errs:
            print(f" - {m}", file=sys.stderr)

    # Overrides from CLI
    table_cfg = spec.setdefault("table", {})
    if ns.level is not None:
        table_cfg["level"] = int(ns.level)
    if ns.bubble is not None:
        table_cfg["bubble"] = bool(ns.bubble)
    odds_policy = ns.odds_policy

    # Telemetry (optional)
    tele = Telemetry(ns.telemetry) if ns.telemetry else None
    final_bankroll = None

    try:
        strat = ControlStrategy(spec, telemetry=tele, odds_policy=odds_policy)

        # Build table
        level = int(table_cfg.get("level", 10))
        bubble = bool(table_cfg.get("bubble", False))
        table_cls = getattr(craps, "Table", None)
        if table_cls is None:
            print("Error: craps.Table not found in engine.", file=sys.stderr)
            return 2

        t = table_cls(level=level, bubble=bubble)
        t.add_player(strat)

        # Run
        t.run(shooters=int(ns.shooters))

        # Best-effort: grab bankroll for summary (may be None if engine doesn’t set it)
        final_bankroll = strat.state.get("bankroll")

    finally:
        if tele is not None:
            tele.close()

    # Always print a "Bankroll …" line for smoke tests
    if final_bankroll is None:
        print("Bankroll: N/A")
    else:
        print(f"Bankroll: {final_bankroll}")

    return 0


def main(argv: list[str] | None = None) -> int:
    ns = _parse_args(sys.argv[1:] if argv is None else argv)
    if ns.cmd == "validate":
        return _cmd_validate(ns.spec, strict=ns.strict)
    if ns.cmd == "run":
        return _cmd_run(ns)
    print("Unknown command", file=sys.stderr)
    return 2