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
    if isinstance(res, tuple) and len(res) == 3:
        ok, hard_errs, soft_warns = res
        return bool(ok), list(hard_errs), list(soft_warns)
    hard_errs = list(res) if isinstance(res, (list, tuple)) else [str(res)]
    ok = len(hard_errs) == 0
    return ok, hard_errs, []


def _engine_unavailable(reason: str | Exception = "missing or incompatible engine") -> int:
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


def _reseed_engine(seed: Optional[int]) -> None:
    if seed is None:
        return
    try:
        import crapssim.dice as dice_mod  # type: ignore
        if hasattr(dice_mod, "set_seed"):
            dice_mod.set_seed(seed)
            return
        if hasattr(dice_mod, "Dice"):
            d = dice_mod.Dice()
            if hasattr(d, "seed"):
                d.seed(seed)  # type: ignore[attr-defined]
    except Exception as e:
        log.debug("Engine reseed skipped: %s", e)


def _force_seed_on_table(table: Any, seed: Optional[int]) -> None:
    if seed is None:
        return
    try:
        import numpy as _np  # type: ignore
        _has_numpy = True
    except Exception:
        _np = None
        _has_numpy = False

    def _is_np_generator(obj: Any) -> bool:
        return _has_numpy and hasattr(obj, "bit_generator") and callable(getattr(obj, "random", None))

    def _try_seed_leaf(obj: Any) -> bool:
        try:
            if hasattr(obj, "set_seed"):
                obj.set_seed(seed)
                return True
            if hasattr(obj, "seed"):
                obj.seed(seed)
                return True
        except Exception:
            pass
        try:
            for attr in ("random", "_random"):
                r = getattr(obj, attr, None)
                if isinstance(r, random.Random):
                    r.seed(seed)
                    return True
        except Exception:
            pass
        if _has_numpy:
            try:
                for attr in ("rng", "_rng"):
                    g = getattr(obj, attr, None)
                    if g is not None and _is_np_generator(g):
                        setattr(obj, attr, _np.random.default_rng(seed))
                        return True
            except Exception:
                pass
        return False

    for attr in ("dice", "_dice", "rng", "_rng"):
        if hasattr(table, attr) and _try_seed_leaf(getattr(table, attr)):
            return
    for parent_attr in ("game", "engine", "_engine", "_game"):
        parent = getattr(table, parent_attr, None)
        if parent is None:
            continue
        for attr in ("dice", "_dice", "rng", "_rng"):
            obj = getattr(parent, attr, None)
            if obj is not None and _try_seed_leaf(obj):
                return
    log.debug("Could not locate dice/rng on table to force seed")


def _run_table_rolls(table: Any, rolls: int) -> Tuple[bool, str]:
    if hasattr(table, "play"):
        try:
            table.play(rolls=rolls)
            return True, "table.play(rolls=...)"
        except Exception as e:
            log.debug("table.play failed: %s", e)
    if hasattr(table, "run"):
        try:
            table.run(rolls)
            return True, "table.run(rolls)"
        except TypeError:
            try:
                table.run(rolls=rolls)
                return True, "table.run(rolls=...)"
            except Exception as e:
                log.debug("table.run failed: %s", e)
        except Exception as e:
            log.debug("table.run failed: %s", e)
    if hasattr(table, "roll"):
        try:
            for _ in range(rolls):
                table.roll()
            return True, "loop: table.roll()"
        except Exception as e:
            log.debug("loop table.roll failed: %s", e)
    try:
        from crapssim.dice import Dice  # type: ignore
        dice = Dice()
        process = getattr(table, "process_roll", None) or getattr(table, "on_roll", None)
        if callable(process):
            for _ in range(rolls):
                r = dice.roll()
                process(r)
            return True, "loop: dice.roll() -> table.process_roll/on_roll"
    except Exception as e:
        log.debug("Dice path unavailable: %s", e)
    return False, "No compatible run method found"


def _write_csv_summary(path: str | Path, row: Dict[str, Any]) -> None:
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


def _lazy_validate_spec(spec: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    try:
        from . import spec_validation as _sv  # lazy
        res = _sv.validate_spec(spec)
    except Exception as e:
        log.debug("validate_spec unavailable or failed: %r", e)
        return False, [f"Validation logic unavailable: {e!r}"], []
    return _normalize_validate_result(res)


def _csv_journal_info(spec: Dict[str, Any]) -> Optional[str]:
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


def _scrub_inert_env() -> None:
    return


def _cmd_journal_summarize(args: argparse.Namespace) -> int:
    from .csv_summary import summarize_journal, write_summary_csv
    jp = Path(args.journal)
    if not jp.exists():
        print(f"failed: journal not found: {jp}", file=sys.stderr)
        return 2
    summaries = summarize_journal(journal_path=jp, group_by_run_id=not args.no_group)
    if args.out:
        try:
            write_summary_csv(summaries, args.out, append=args.append)
        except Exception as e:
            print(f"failed: {e}", file=sys.stderr)
            return 2
    cols = [
        "run_id", "rows_total", "actions_total",
        "sets", "clears", "presses", "reduces", "switch_mode",
        "unique_bets", "modes_used", "points_seen",
        "roll_events", "regress_events",
        "sum_amount_set", "sum_amount_press", "sum_amount_reduce",
        "first_timestamp", "last_timestamp",
        "path",
    ]
    print("\t".join(["run_id_or_file"] + cols[1:]))
    for s in summaries:
        row = [str(s.get(c, "")) for c in cols]
        print("\t".join(row))
    return 0


def run(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    spec = _load_spec_file(spec_path)

    spec_run = spec.get("run", {}) if isinstance(spec.get("run", {}), dict) else {}
    rolls = int(args.rolls) if args.rolls is not None else int(spec_run.get("rolls", 1000))
    seed = args.seed if args.seed is not None else spec_run.get("seed")

    demo_fallbacks = bool(getattr(args, "demo_fallbacks", False))
    strict = bool(getattr(args, "strict", False))
    embed_analytics = not bool(getattr(args, "no_embed_analytics", False))
    if log.isEnabledFor(logging.DEBUG):
        log.debug("P0·C1 flags (inert): demo_fallbacks=%s strict=%s embed_analytics=%s",
                  demo_fallbacks, strict, embed_analytics)

    if os.environ.get("CSC_SKIP_VALIDATE", "0").lower() not in ("1", "true", "yes"):
        ok, hard_errs, soft_warns = _lazy_validate_spec(spec)
        if not ok or hard_errs:
            print("failed validation:", file=sys.stderr)
            for e in hard_errs:
                print(f"- {e}", file=sys.stderr)
            return 2
        for w in soft_warns:
            log.warning("spec warning: %s", w)

    info = _csv_journal_info(spec)
    if info:
        print(info)

    seed_int = None
    if seed is not None:
        try:
            seed_int = int(seed)
        except Exception:
            seed_int = None
    _smart_seed(seed_int)
    _reseed_engine(seed_int)

    try:
        from crapssim_control.engine_adapter import EngineAdapter
        adapter = EngineAdapter()
        attach_result = adapter.attach(spec)
        table = attach_result.table
        _force_seed_on_table(table, seed_int)

        # NEW: post-attach reseed hook and optional audit
        try:
            adapter.set_seed(seed_int)
        except Exception:
            pass

        rng_audit = bool(getattr(args, "rng_audit", False)) or os.environ.get("CSC_RNG_AUDIT", "") in ("1", "true", "yes")
        if rng_audit:
            src = "CLI --seed" if seed_int is not None else "spec/run.seed or default"
            print(f"[rng-audit] seeded python.random + numpy.random (legacy); adapter.set_seed invoked; source={src}")

        log.debug("attach meta: %s", getattr(attach_result, "meta", {}))
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("DEBUG attach_result:", getattr(attach_result, "meta", {}))
    except Exception as e:
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("\n--- CSC DEBUG TRACEBACK (attach) ---", flush=True)
            traceback.print_exc()
            print("--- END CSC DEBUG ---\n", flush=True)
        return _engine_unavailable(e)

    log.info("Starting run: rolls=%s seed=%s", rolls, seed_int)
    ok, used = _run_table_rolls(table, rolls)
    if not ok:
        msg = f"Could not run {rolls} rolls. {used}."
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("\n--- CSC DEBUG: run failure ---", msg, "\n", flush=True)
        return _engine_unavailable(msg)

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

    if getattr(args, "export", None):
        try:
            _write_csv_summary(
                args.export,
                {
                    "spec": str(spec_path),
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


def _cmd_validate(args: argparse.Namespace) -> int:
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
            from .guardrails import apply_guardrails
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
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="increase verbosity (use -vv for debug)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="Validate a strategy spec (JSON or YAML)")
    p_val.add_argument("spec", help="Path to spec file")
    p_val.add_argument("--hot-table", action="store_true", dest="hot_table",
                       help='Plan with "hot table" defaults (no behavior change yet)')
    p_val.add_argument("--guardrails", action="store_true",
                       help="Print guardrail planning notes (no behavior change yet)")
    p_val.set_defaults(func=_cmd_validate)

    p_run = sub.add_parser("run", help="Run a simulation for a given spec")
    p_run.add_argument("spec", help="Path to spec file")
    p_run.add_argument("--rolls", type=int, help="Number of rolls (overrides spec)")
    p_run.add_argument("--seed", type=int, help="Seed RNG for reproducibility")
    p_run.add_argument("--export", type=str, help="Path to CSV summary export (optional)")
    p_run.add_argument("--demo-fallbacks", action="store_true",
                       help="(scaffold) Enable demo fallbacks. P0·C1: no behavior change.")
    p_run.add_argument("--strict", action="store_true",
                       help="(scaffold) Enable strict/advisory enforcement. P0·C1: no behavior change.")
    p_run.add_argument("--no-embed-analytics", action="store_true", dest="no_embed_analytics",
                       help="(scaffold) Disable embedding analytics in CSV. P0·C1: no behavior change.")
    # NEW FLAG
    p_run.add_argument("--rng-audit", action="store_true",
                       help="Print RNG seeding audit info (debug aid; no behavior change).")
    p_run.set_defaults(func=_cmd_run)

    p_j = sub.add_parser("