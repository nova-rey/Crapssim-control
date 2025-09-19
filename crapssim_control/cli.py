from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path
from typing import Any, Dict

from . import __version__
from .spec_validation import validate_spec
from .logging_utils import setup_logging
from .flags import ensure_meta_flags, set_flag

# Optional YAML support
try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


def _load_spec_file(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        if yaml is None:
            raise RuntimeError("PyYAML not installed; cannot read YAML specs.")
        return yaml.safe_load(text) or {}
    # default JSON
    return json.loads(text or "{}")


def _normalize_validate_result(res):
    """
    Accept either:
      • (ok: bool, hard_errs: list[str], soft_warns: list[str])
      • hard_errs: list[str]
    Return (ok, hard_errs, soft_warns)
    """
    if isinstance(res, tuple) and len(res) == 3:
        ok, hard_errs, soft_warns = res
        return bool(ok), list(hard_errs), list(soft_warns)
    # legacy: just a list of hard errors
    hard_errs = list(res) if isinstance(res, (list, tuple)) else [str(res)]
    ok = len(hard_errs) == 0
    return ok, hard_errs, []


def _print_failed(errors: list[str]) -> None:
    """
    Standardized failure block to stderr, plus legacy-friendly aliases
    for certain messages that older tests expect.
    """
    print("failed validation:", file=sys.stderr)
    needs_modes_alias = False
    for e in errors:
        print(f"- {e}", file=sys.stderr)
        if "Missing required section: 'modes'" in e:
            needs_modes_alias = True
    # Legacy-friendly alias line for tests expecting this exact wording
    if needs_modes_alias:
        print("- modes section is required", file=sys.stderr)


def _cmd_validate(args: argparse.Namespace) -> int:
    """
    Output contract (tests rely on this):
      - success -> stdout contains 'OK:' and path
      - failure -> stderr starts with 'failed validation:' and lists bullets
    """
    spec_path = Path(args.spec)
    try:
        spec = _load_spec_file(spec_path)
    except Exception as e:
        print(f"failed validation:\n- Could not load spec: {e}", file=sys.stderr)
        return 2

    # Record flags if provided (no behavior change; just serialize into the spec)
    ensure_meta_flags(spec)
    if args.hot_table:
        set_flag(spec, "hot_table", True)
    if args.guardrails:
        set_flag(spec, "guardrails", True)

    res = validate_spec(spec)  # compatible with both return styles
    ok, hard_errs, soft_warns = _normalize_validate_result(res)
    if ok and not hard_errs:
        print(f"OK: {spec_path}")
        if soft_warns and args.verbose:
            for w in soft_warns:
                print(f"warn: {w}")
        return 0

    _print_failed(hard_errs)
    return 2


def _cmd_run(args: argparse.Namespace) -> int:
    """
    Simple runner around CrapsSim + our strategy.
    """
    setup_logging(args.verbose)
    log = logging.getLogger("crapssim-ctl")

    # Load spec
    try:
        spec = _load_spec_file(args.spec)
    except Exception as e:
        log.error("Could not load spec: %s", e)
        print(f"failed: Could not load spec: {e}", file=sys.stderr)
        return 2

    # Persist flags from CLI (no behavior change yet; just serializing)
    ensure_meta_flags(spec)
    if args.hot_table:
        set_flag(spec, "hot_table", True)
    if args.guardrails:
        set_flag(spec, "guardrails", True)

    # Validate spec (hard errors stop)
    res = validate_spec(spec)
    ok, hard_errs, soft_warns = _normalize_validate_result(res)
    if not ok or hard_errs:
        _print_failed(hard_errs)
        return 2

    if soft_warns:
        for w in soft_warns:
            log.warning("spec warning: %s", w)

    # Import CrapsSim lazily
    try:
        from crapssim.table import Table
        from crapssim.player import Player
        from crapssim.dice import Dice
    except Exception as e:  # pragma: no cover
        log.error("CrapsSim engine not available: %s", e)
        print("failed: CrapsSim engine not available (pip install crapssim).", file=sys.stderr)
        return 2

    # Strategy + adapter
    try:
        from .controller import ControlStrategy
        from .engine_adapter import EngineAdapter
    except Exception as e:  # pragma: no cover
        log.error("Internal import error: %s", e)
        print(f"failed: internal import error: {e}", file=sys.stderr)
        return 2

    # Build table environment
    bubble = bool(args.bubble) if args.bubble is not None else bool(spec.get("table", {}).get("bubble", False))
    level = int(args.level) if args.level is not None else int(spec.get("table", {}).get("level", 10))
    seed = args.seed
    if seed is not None:
        random.seed(seed)

    dice = Dice(seed=seed)
    table = Table(bubble=bubble, level=level, dice=dice)
    player = Player(name="Strategy")
    table.add_player(player)

    strat = ControlStrategy(spec)
    adapter = EngineAdapter(table, player, strat)

    rolls = int(args.rolls or 1000)
    log.info("Starting run: rolls=%s bubble=%s level=%s seed=%s", rolls, bubble, level, seed)

    adapter.play(rolls=rolls)

    # Summarize results
    bankroll = getattr(player, "bankroll", None)
    if bankroll is not None:
        print(f"RESULT: rolls={rolls} bankroll={bankroll:.2f}")
    else:
        print(f"RESULT: rolls={rolls}")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crapssim-ctl",
        description="Crapssim Control - validate specs and run simulations"
    )
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="increase verbosity (use -vv for debug)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    # validate
    p_val = sub.add_parser("validate", help="Validate a strategy spec (JSON or YAML)")
    p_val.add_argument("spec", help="Path to spec file")
    # Feature flags (hard-off by default)
    p_val.add_argument("--hot-table", action="store_true", help="Enable experimental hot-table scaling (OFF by default)")
    p_val.add_argument("--guardrails", action="store_true", help="Enable experimental guardrails (OFF by default)")
    p_val.set_defaults(func=_cmd_validate)

    # run
    p_run = sub.add_parser("run", help="Run a simulation for a given spec")
    p_run.add_argument("spec", help="Path to spec file")
    p_run.add_argument("--rolls", type=int, default=1000, help="Number of rolls")
    p_run.add_argument("--bubble", action="store_true", help="Force bubble table")
    p_run.add_argument("--level", type=int, help="Override table level (min bet)")
    p_run.add_argument("--seed", type=int, help="Seed RNG for reproducibility")
    # Feature flags (hard-off by default)
    p_run.add_argument("--hot-table", action="store_true", help="Enable experimental hot-table scaling (OFF by default)")
    p_run.add_argument("--guardrails", action="store_true", help="Enable experimental guardrails (OFF by default)")
    p_run.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    # Back-compat shim: allow `validate <path>` without requiring subparser in unusual embeddings
    if argv and argv[0] == "validate":
        parser = _build_parser()
        args = parser.parse_args(argv)
        return args.func(args)

    parser = _build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())