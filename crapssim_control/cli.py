"""
Simple CLI to run a Craps strategy spec with the CrapsSim engine.

Usage (after pip install -e .):
  crapssim-ctl --spec examples/martingale_pass.json --rolls 200

This stays out of the test path and doesn’t change library behavior.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Dict, Optional

try:
    import crapssim as cs  # Engine
except Exception as e:  # pragma: no cover - CLI only
    cs = None
    _ENGINE_IMPORT_ERR = e
else:
    _ENGINE_IMPORT_ERR = None

from .controller import ControlStrategy  # our strategy driver
from .engine_adapter import EngineAdapter
from .spec_validation import assert_valid_spec


def _load_spec(path: str | pathlib.Path) -> Dict[str, Any]:
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Spec file not found: {p}")

    # JSON only (no extra deps). If you want YAML later, feel free to add PyYAML.
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _build_table(bubble: bool, level: int, seed: Optional[int]) -> Any:
    """
    Build a minimal CrapsSim table + one player.
    We keep this tiny and only use stable surface area.
    """
    if cs is None:  # pragma: no cover
        raise RuntimeError(
            "CrapsSim engine not available. "
            f"Import error: {_ENGINE_IMPORT_ERR!r}"
        )

    rng = cs.Random(seed) if seed is not None else cs.Random()
    rules = cs.TableRules()  # default 3-4-5 odds
    table = cs.Table(rules=rules, rng=rng, bubble=bubble, min_bet=level)
    return table


def run_once(spec_path: str, *, rolls: int, bubble: bool, level: int, seed: Optional[int]) -> Dict[str, Any]:
    spec = _load_spec(spec_path)
    # Validate (raises with helpful message if not valid)
    assert_valid_spec(spec)

    # Build engine objects
    table = _build_table(bubble=bubble, level=level, seed=seed)
    player = cs.Player("You")  # type: ignore[attr-defined]  # pragma: no cover in tests

    table.add_player(player)   # type: ignore[operator]      # pragma: no cover in tests

    # Wire strategy
    strat = ControlStrategy(spec)
    adapter = EngineAdapter(table, player, strat)

    # Warmup: send a comeout to seed any template-on-comeout rules
    if hasattr(strat, "handle_event"):
        strat.handle_event({"type": "comeout"}, current_bets={})

    # Play N rolls with our adapter (no external engine loop needed)
    adapter.play(shooters=1, max_rolls=rolls)

    # Summarize
    bankroll = getattr(player, "bankroll", None)
    stats = {
        "rolls": rolls,
        "final_bankroll": float(bankroll) if bankroll is not None else None,
        "bubble": bubble,
        "table_level": level,
        "seed": seed,
    }
    return stats


def main(argv: Optional[list[str]] = None) -> int:  # pragma: no cover - CLI entry
    parser = argparse.ArgumentParser(
        prog="crapssim-ctl",
        description="Run a Craps strategy spec with the CrapsSim engine."
    )
    parser.add_argument("--spec", required=True, help="Path to a JSON spec file.")
    parser.add_argument("--rolls", type=int, default=200, help="Number of rolls to run (default: 200).")
    parser.add_argument("--bubble", action="store_true", help="Run on a bubble table (default: False).")
    parser.add_argument("--level", type=int, default=10, help="Table minimum in dollars (default: 10).")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")

    args = parser.parse_args(argv)

    try:
        result = run_once(
            args.spec,
            rolls=args.rolls,
            bubble=args.bubble,
            level=args.level,
            seed=args.seed,
        )
    except Exception as e:
        print(f"[crapssim-ctl] Error: {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())