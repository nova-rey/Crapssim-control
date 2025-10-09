from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

from .logging_utils import setup_logging

log = logging.getLogger("crapssim-ctl")

# Optional YAML support
try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


# ------------------------------- Helpers ------------------------------------ #

def _load_spec_file(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        if yaml is None:
            raise RuntimeError("PyYAML not installed; cannot read YAML specs.")
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text or "{}")
    if not isinstance(data, dict):
        raise ValueError("Spec root must be a JSON/YAML object (mapping).")
    return data


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
    hard_errs = list(res) if isinstance(res, (list, tuple)) else [str(res)]
    ok = len(hard_errs) == 0
    return ok, hard_errs, []


def _engine_unavailable(reason: str | Exception = "missing or incompatible engine") -> int:
    """
    Standardized failure for tests, while logging the real reason.
    """
    msg = "CrapsSim engine not available (pip install crapssim)."
    log.error("%s Reason: %s", msg, reason)
    print(f"failed: {msg}", file=sys.stderr)
    return 2


def _smart_seed(seed: Optional[int]) -> None:
    if seed is not None:
        random.seed(seed)
        try:
            import numpy as _np  # type: ignore
            _np.random.seed(seed)
        except Exception:
            pass


def _run_table_rolls(table: Any, rolls: int) -> Tuple[bool, str]:
    """
    Try several ways to drive the Table for N rolls.
    Returns (ok, detail). Never raises.
    """
    # 1) table.play(rolls=...)
    if hasattr(table, "play"):
        try:
            table.play(rolls=rolls)
            return True, "table.play(rolls=...)"
        except Exception as e:
            log.debug("table.play failed: %s", e)

    # 2) table.run(rolls)  or  table.run(rolls=...)
    if hasattr(table, "run"):
        try:
            table.run(rolls)  # type: ignore[arg-type]
            return True, "table.run(rolls)"
        except TypeError:
            try:
                table.run(rolls=rolls)
                return True, "table.run(rolls=...)"
            except Exception as e:
                log.debug("table.run failed: %s", e)
        except Exception as e:
            log.debug("table.run failed: %s", e)

    # 3) Manual loop: table.roll()
    if hasattr(table, "roll"):
        try:
            for _ in range(rolls):
                table.roll()
            return True, "loop: table.roll()"
        except Exception as e:
            log.debug("loop table.roll failed: %s", e)

    # 4) Manual loop with Dice: dice.roll() + table.process_roll/on_roll
    try:
        from crapssim.dice import Dice  # type: ignore
        dice = Dice()
        process = getattr(table, "process_roll", None) or getattr(table, "on_roll", None)
        if callable(process):
            try:
                for _ in range(rolls):
                    r = dice.roll()
                    process(r)
                return True, "loop: dice.roll() -> table.process_roll/on_roll"
            except Exception as e:
                log.debug("loop dice->process failed: %s", e)
    except Exception as e:
        log.debug("Dice path unavailable: %s", e)

    return False, "No compatible run method found"


def _write_csv_summary(path: str | Path, row: Dict[str, Any]) -> None:
    """
    Append a one-line summary CSV. Creates file and header if needed.
    Fields (in order): spec, rolls, final_bankroll, seed, note
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["spec", "rolls", "final_bankroll", "seed", "note"]

    write_header = True
    if path.exists():
        try:
            write_header = path.stat().st_size == 0
        except Exception:
            write_header = False

    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        safe_row = {
            "spec": str(row.get("spec", "")),
            "rolls": int(row.get("rolls", 0)),
            "final_bankroll": float(row.get("final_bankroll", 0.0)) if row.get("final_bankroll") is not None else "",
            "seed": "" if row.get("seed") is None else str(row.get("seed")),
            "note": str(row.get("note", "")),
        }
        writer.writerow(safe_row)


# ------------------------------ Validation ---------------------------------- #

def _lazy_validate_spec(spec: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    """
    Lazy-import validate_spec to avoid import-time failures if that module
    still has TODOs. Always returns (ok, hard_errs, soft_warns).
    """
    try:
        from . import spec_validation as _sv  # lazy
        res = _sv.validate_spec(spec)
    except Exception as e:
        log.debug("validate_spec unavailable or failed: %r", e)
        return False, [f"Validation logic unavailable: {e!r}"], []
    return _normalize_validate_result(res)


# ------------------------------ CSV Journal FYI ------------------------------ #

def _csv_journal_info(spec: Dict[str, Any]) -> Optional[str]:
    """
    Read spec.run.csv and return a tiny human-friendly summary if journaling is enabled.
    This is FYI only; the controller actually does the writing.
    """
    run = spec.get("run", {}) if isinstance(spec.get("run", {}), dict) else {}
    csv_cfg = run.get("csv") if isinstance(run, dict) else None
    if not isinstance(csv_cfg, dict):
        return None
    if not csv_cfg.get("enabled"):
        return None
    path = csv_cfg.get("path")
    if not path:
        return None
    append = csv_cfg.get("append", True)
    return f"[journal] enabled → {path} (append={'on' if append else 'off'})"


# --------------------------------- Run -------------------------------------- #

def run(args: argparse.Namespace) -> int:
    """
    Run path:
      1) Load & validate spec
      2) Compute rolls/seed: CLI overrides > spec values > defaults
      3) Attach engine via EngineAdapter (modern strategy attach)
      4) Drive the table for N rolls using the most compatible method found
      5) Print result summary (+ optional CSV export)
    """
    # Load spec (JSON or YAML)
    spec_path = Path(args.spec)
    spec = _load_spec_file(spec_path)

    # --- Read runtime settings from the spec (optional) ---
    spec_run = spec.get("run", {}) if isinstance(spec.get("run", {}), dict) else {}

    # Prefer CLI; otherwise spec; fallback default
    rolls = int(args.rolls) if args.rolls is not None else int(spec_run.get("rolls", 1000))
    seed = args.seed if args.seed is not None else spec_run.get("seed")

    # Validate first (fail fast)
    ok, hard_errs, soft_warns = _lazy_validate_spec(spec)
    if not ok or hard_errs:
        print("failed validation:", file=sys.stderr)
        for e in hard_errs:
            print(f"- {e}", file=sys.stderr)
        return 2
    for w in soft_warns:
        log.warning("spec warning: %s", w)

    # Friendly FYI if journaling is configured in the spec
    info = _csv_journal_info(spec)
    if info:
        print(info)

    # Seed RNGs (Python & NumPy)
    if seed is not None:
        try:
            seed_int = int(seed)
        except Exception:
            seed_int = None
        _smart_seed(seed_int)
    else:
        seed_int = None

    # Attach engine (modern adapter handles CrapsSim 0.3+; legacy fallback inside)
    try:
        from crapssim_control.engine_adapter import EngineAdapter  # lazy
        adapter = EngineAdapter()
        attach_result = adapter.attach(spec)  # -> EngineAttachResult
        table = attach_result.table
        log.debug("attach meta: %s", getattr(attach_result, "meta", {}))
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("DEBUG attach_result:", getattr(attach_result, "meta", {}))
    except Exception as e:
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("\n--- CSC DEBUG TRACEBACK (attach) ---", flush=True)
            traceback.print_exc()
            print("--- END CSC DEBUG ---\n", flush=True)
        return _engine_unavailable(e)

    # Drive the table
    log.info("Starting run: rolls=%s seed=%s", rolls, seed_int)
    ok, used = _run_table_rolls(table, rolls)
    if not ok:
        msg = f"Could not run {rolls} rolls. {used}."
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("\n--- CSC DEBUG: run failure ---", msg, "\n", flush=True)
        return _engine_unavailable(msg)

    # Summarize results (best-effort)
    bankroll = None
    try:
        players = getattr(table, "players", None)
        if players and len(players) > 0:
            p0 = players[0]
            bankroll = getattr(p0, "bankroll", None)
    except Exception:
        pass

    if bankroll is not None:
        print(f"RESULT: rolls={rolls} bankroll={float(bankroll):.2f}")
    else:
        print(f"RESULT: rolls={rolls}")

    # Optional CSV export (end-of-run summary)
    if getattr(args, "export", None):
        try:
            _write_csv_summary(
                args.export,
                {
                    "spec": str(Path(args.spec)),
                    "rolls": rolls,
                    "final_bankroll": float(bankroll) if bankroll is not None else None,
                    "seed": seed_int,
                    "note": getattr(getattr(attach_result, "meta", {}), "get", lambda _k, _d=None: _d)("mode", ""),
                },
            )
            log.info("Exported summary CSV → %s", args.export)
            if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
                print(f"[CSV] wrote summary to {args.export}")
        except Exception as e:
            print(f"warn: export failed: {e}", file=sys.stderr)

    return 0


# ------------------------------ Journal Summarize ---------------------------- #

def _cmd_journal_summarize(args: argparse.Namespace) -> int:
    """
    Summarize a journal CSV and either print a table to stdout or write a summary CSV.
    """
    from .csv_summary import summarize_journal, write_summary_csv

    try:
        journal_path = Path(args.journal)
        if not journal_path.exists() or not journal_path.is_file():
            print(f"failed: journal not found: {journal_path}", file=sys.stderr)
            return 2

        group_by_run_id = True if args.by_run_id else False
        summaries = summarize_journal(journal_path=journal_path, group_by_run_id=group_by_run_id)

        if args.out:
            out_path = Path(args.out)
            write_summary_csv(out_path, summaries, append=bool(args.append))
            print(f"wrote summary → {out_path}")
            return 0

        # Pretty print to stdout (minimal, deterministic column order)
        cols = [
            "run_id_or_file",
            "rows_total",
            "actions_total",
            "sets",
            "presses",
            "reduces",
            "clears",
            "switch_mode",
            "unique_bets",
            "modes_used",
            "points_seen",
            "roll_events",
            "t_first",
            "t_last",
        ]

        # Header
        print("\t".join(cols))
        for s in summaries:
            row = [str(s.get(c, "")) for c in cols]
            print("\t".join(row))
        return 0

    except Exception as e:
        log.debug("journal summarize failed", exc_info=True)
        print(f"failed: {e}", file=sys.stderr)
        return 2


# ------------------------------ Parser/Main --------------------------------- #

def _cmd_validate(args: argparse.Namespace) -> int:
    """
    Output:
      - success -> stdout contains 'OK:' and path
      - failure -> stderr starts with 'failed validation:' and lists bullets
    """
    spec_path = Path(args.spec)
    try:
        spec = _load_spec_file(spec_path)
    except Exception as e:
        print(f"failed validation:\n- Could not load spec: {e}", file=sys.stderr)
        return 2

    ok, hard_errs, soft_warns = _lazy_validate_spec(spec)

    notes: List[str] = []
    if getattr(args, "guardrails", False):
        try:
            from .guardrails import apply_guardrails  # lazy import
            _spec2, note_lines = apply_guardrails(
                spec,
                hot_table=getattr(args, "hot_table", False),
                guardrails=True,
            )
            notes.extend(note_lines)
        except Exception:
            pass

    if ok and not hard_errs:
        print(f"OK: {spec_path}")
        if notes and args.verbose:
            for w in notes:
                print(f"note: {w}")
        if soft_warns and args.verbose:
            for w in soft_warns:
                print(f"warn: {w}")
        return 0

    print("failed validation:", file=sys.stderr)
    for e in hard_errs:
        print(f"- {e}", file=sys.stderr)
    if any("Missing required section: 'modes'" in e for e in hard_errs):
        print("- modes section is required", file=sys.stderr)
    return 2


def _cmd_run(args: argparse.Namespace) -> int:
    # Delegate to run(); if it throws, print traceback when CSC_DEBUG is set.
    try:
        return run(args)
    except Exception:
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("\n--- CSC DEBUG TRACEBACK ---", flush=True)
            traceback.print_exc()
            print("--- END CSC DEBUG ---\n", flush=True)
        raise


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crapssim-ctl",
        description="Crapssim Control - validate specs and run simulations",
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="increase verbosity (use -vv for debug)",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    # validate
    p_val = sub.add_parser("validate", help="Validate a strategy spec (JSON or YAML)")
    p_val.add_argument("spec", help="Path to spec file")
    p_val.add_argument("--hot-table", action="store_true", dest="hot_table",
                       help='Plan with "hot table" defaults (no behavior change yet)')
    p_val.add_argument("--guardrails", action="store_true",
                       help="Print guardrail planning notes (no behavior change yet)")
    p_val.set_defaults(func=_cmd_validate)

    # run
    p_run = sub.add_parser("run", help="Run a simulation for a given spec")
    p_run.add_argument("spec", help="Path to spec file")
    p_run.add_argument("--rolls", type=int, help="Number of rolls (overrides spec)")
    p_run.add_argument("--seed", type=int, help="Seed RNG for reproducibility")
    p_run.add_argument("--export", type=str, help="Path to CSV summary export (optional)")
    p_run.set_defaults(func=_cmd_run)

    # journal summarize
    p_journal = sub.add_parser("journal", help="CSV journal utilities")
    p_journal_sub = p_journal.add_subparsers(dest="journal_cmd", required=True)

    p_sum = p_journal_sub.add_parser("summarize", help="Summarize a journal CSV")
    p_sum.add_argument("journal", help="Path to journal CSV")
    g = p_sum.add_mutually_exclusive_group()
    g.add_argument("--by-run-id", action="store_true", default=True,
                   help="Group summary rows by run_id (default)")
    g.add_argument("--by-file", action="store_true",
                   help="Single summary row per file (ignore run_id)")
    p_sum.add_argument("--out", type=str, default=None,
                       help="Path to write summary CSV; omit to print to stdout")
    p_sum.add_argument("--append", action="store_true", default=False,
                       help="Append to the output summary CSV (creates file if missing)")
    p_sum.set_defaults(func=_cmd_journal_summarize)

    return parser


def main(argv: List[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    # Normalize journal grouping flags for convenience
    if getattr(args, "cmd", None) == "journal" and getattr(args, "journal_cmd", None) == "summarize":
        # If --by-file is set, disable by-run-id
        if getattr(args, "by_file", False):
            args.by_run_id = False
        else:
            args.by_run_id = True

    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())