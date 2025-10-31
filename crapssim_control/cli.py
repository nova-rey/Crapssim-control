from __future__ import annotations

import argparse
import csv
import copy
import inspect
import json
import logging
import os
import random
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from . import __version__ as CSC_VERSION
from .cli_flags import CLIFlags, parse_flags
from .config import (
    EMBED_ANALYTICS_DEFAULT,
    STRICT_DEFAULT,
    coerce_flag,
    get_policy_options,
    get_stop_options,
    normalize_demo_fallbacks,
)
from .commands import doctor_run, init_run, summarize_run
from .logging_utils import setup_logging
from .policy_engine import PolicyEngine
from .risk_schema import load_risk_policy
from .spec_validation import VALIDATION_ENGINE_VERSION
from .spec_loader import load_spec_file
from .rules_engine.author import RuleBuilder
from .schemas import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION
from .run.decisions_trace import DecisionsTrace
from .manifest import generate_manifest

log = logging.getLogger("crapssim-ctl")

# Optional YAML support
try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


# ------------------------------- Helpers ------------------------------------ #


def _load_spec_file(path: str | Path) -> Dict[str, Any]:
    spec, _ = load_spec_file(path)
    return spec


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

            _np.random.seed(seed)  # affects legacy RandomState only
        except Exception:
            pass


def _reseed_engine(seed: Optional[int]) -> None:
    """
    Reset any module-level engine RNGs (best-effort).
    """
    if seed is None:
        return
    try:
        import crapssim.dice as dice_mod  # type: ignore

        # Prefer an explicit module hook, if present
        if hasattr(dice_mod, "set_seed"):
            dice_mod.set_seed(seed)
            return
        # Fall back to a Dice() helper, if it exposes a seed method
        if hasattr(dice_mod, "Dice"):
            d = dice_mod.Dice()
            if hasattr(d, "seed"):
                d.seed(seed)  # type: ignore[attr-defined]
    except Exception as e:
        log.debug("Engine reseed skipped: %s", e)


def _force_seed_on_table(table: Any, seed: Optional[int]) -> None:
    """
    Ensure the *actual* dice/RNG instance the table uses is seeded.
    Handles:
      • objects exposing .set_seed(...) or .seed(...)
      • objects carrying a Python random.Random in .random / ._random
      • objects carrying a NumPy Generator in .rng / ._rng (default_rng)
      • 'dice' containers that themselves have an inner .rng / .random
    Never raises; logs at DEBUG on best-effort failures.
    """
    if seed is None:
        return

    # Lazy import numpy only if we need it
    try:
        import numpy as _np  # type: ignore

        _has_numpy = True
    except Exception:
        _np = None
        _has_numpy = False

    def _is_np_generator(obj: Any) -> bool:
        # Heuristic: new API Generators have .bit_generator and .random method
        return (
            _has_numpy and hasattr(obj, "bit_generator") and callable(getattr(obj, "random", None))
        )

    def _try_seed_leaf(obj: Any) -> bool:
        # Direct seeding hooks
        try:
            if hasattr(obj, "set_seed"):
                obj.set_seed(seed)  # type: ignore[attr-defined]
                return True
            if hasattr(obj, "seed"):
                obj.seed(seed)  # type: ignore[attr-defined]
                return True
        except Exception:
            pass

        # random.Random instances living on the object
        try:
            for attr in ("random", "_random"):
                r = getattr(obj, attr, None)
                if isinstance(r, random.Random):
                    r.seed(seed)
                    return True
        except Exception:
            pass

        # NumPy Generator: replace with a freshly seeded one
        if _has_numpy:
            try:
                for attr in ("rng", "_rng"):
                    g = getattr(obj, attr, None)
                    if g is not None and _is_np_generator(g):
                        setattr(obj, attr, _np.random.default_rng(seed))  # type: ignore[attr-defined]
                        return True
            except Exception:
                pass

        return False

    # Common attachment points on the table
    for attr in ("dice", "_dice", "rng", "_rng"):
        if hasattr(table, attr) and _try_seed_leaf(getattr(table, attr)):
            return

    # Some tables hang dice on a game/engine member
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
            "final_bankroll": (
                float(row.get("final_bankroll", 0.0))
                if row.get("final_bankroll") is not None
                else ""
            ),
            "seed": "" if row.get("seed") is None else str(row.get("seed")),
            "note": str(row.get("note", "")),
        }
        writer.writerow(safe_row)


# ------------------------------ Validation ---------------------------------- #


def _lazy_validate_spec(spec: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    try:
        from . import spec_validation as _sv  # lazy

        res = _sv.validate_spec(spec)
    except Exception as e:
        log.debug("validate_spec unavailable or failed: %r", e)
        return False, [f"Validation logic unavailable: {e!r}"], []
    return _normalize_validate_result(res)


# ------------------------------ CSV Journal FYI ------------------------------ #


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


# --------------------------- P0·C1 inert env scrub --------------------------- #


def _scrub_inert_env() -> None:
    """
    NO-OP: we keep CSC_FORCE_SEED intact so both runs in verify share the same
    bootstrap seed path. We do not mutate argv or environment here.
    """
    return


# -------------------------------- Journal cmd -------------------------------- #


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
        "run_id",
        "rows_total",
        "actions_total",
        "sets",
        "clears",
        "presses",
        "reduces",
        "switch_mode",
        "unique_bets",
        "modes_used",
        "points_seen",
        "roll_events",
        "regress_events",
        "sum_amount_set",
        "sum_amount_press",
        "sum_amount_reduce",
        "first_timestamp",
        "last_timestamp",
        "path",
    ]
    print("\t".join(["run_id_or_file"] + cols[1:]))
    for s in summaries:
        row = [str(s.get(c, "")) for c in cols]
        print("\t".join(row))

    return 0


# --------------------------------- Run -------------------------------------- #


def _merge_cli_run_flags(spec: Dict[str, Any], args: argparse.Namespace) -> None:
    """Merge CLI flag overrides into ``spec['run']`` in-place."""

    if not isinstance(spec, dict):
        return

    cli_flags_obj = getattr(args, "_cli_flags", None)
    if not isinstance(cli_flags_obj, CLIFlags):
        cli_flags_obj = CLIFlags(
            strict=bool(getattr(args, "strict", False)),
            demo_fallbacks=bool(getattr(args, "demo_fallbacks", False)),
            embed_analytics=not bool(getattr(args, "no_embed_analytics", False)),
            export=bool(getattr(args, "export", None)),
            explain=bool(getattr(args, "explain", False)),
            webhook_url=getattr(args, "webhook_url", None),
            webhook_timeout=(
                float(getattr(args, "webhook_timeout", 2.0))
                if getattr(args, "webhook_timeout", None) is not None
                else 2.0
            ),
            webhook_enabled=(
                bool(getattr(args, "webhook_url", None))
                and not bool(getattr(args, "no_webhook", False))
            ),
            evo_enabled=bool(getattr(args, "evo_enabled", False)),
            trial_tag=getattr(args, "trial_tag", None),
        )
        if getattr(args, "strict", False):
            cli_flags_obj.strict_source = "cli"
        if getattr(args, "demo_fallbacks", False):
            cli_flags_obj.demo_fallbacks_source = "cli"
        if getattr(args, "no_embed_analytics", False):
            cli_flags_obj.embed_analytics_source = "cli"
        if getattr(args, "export", None):
            cli_flags_obj.export_source = "cli"
        if getattr(args, "webhook_url", None):
            cli_flags_obj.webhook_url_source = "cli"
            cli_flags_obj.webhook_enabled_source = "cli"
        if getattr(args, "no_webhook", False):
            cli_flags_obj.webhook_enabled_source = "cli"
        if getattr(args, "explain", False):
            cli_flags_obj.explain_source = "cli"
        setattr(args, "_cli_flags", cli_flags_obj)

    run_blk = spec.get("run")
    run_dict: Dict[str, Any]
    if isinstance(run_blk, dict):
        run_dict = run_blk
    else:
        run_dict = {}

    changed = False

    sources = run_dict.get("_csc_flag_sources")
    if not isinstance(sources, dict):
        sources = {}

    if cli_flags_obj.demo_fallbacks:
        run_dict["demo_fallbacks"] = True
        sources["demo_fallbacks"] = "cli"
        changed = True

    if cli_flags_obj.strict:
        run_dict["strict"] = True
        sources["strict"] = "cli"
        changed = True

    if cli_flags_obj.explain:
        journal_blk = run_dict.get("journal")
        if not isinstance(journal_blk, dict):
            journal_blk = {}
        journal_blk["dsl_trace"] = True
        run_dict["journal"] = journal_blk
        sources["explain"] = "cli"
        changed = True

    if not cli_flags_obj.embed_analytics:
        csv_blk = run_dict.get("csv")
        if not isinstance(csv_blk, dict):
            csv_blk = {}
        csv_blk["embed_analytics"] = False
        run_dict["csv"] = csv_blk
        sources["embed_analytics"] = "cli"
        changed = True

    if sources:
        run_dict["_csc_flag_sources"] = sources
    elif "_csc_flag_sources" in run_dict:
        run_dict.pop("_csc_flag_sources", None)

    if changed or isinstance(run_blk, dict):
        # Preserve existing dict reference or attach a new run block if needed.
        spec["run"] = run_dict


def _prepare_run_artifacts(
    spec: Dict[str, Any],
    spec_path: Path,
    args: argparse.Namespace,
) -> Tuple[Path, str, Optional[DecisionsTrace], bool, str]:
    """Ensure per-run artifact directories and tracing writers are ready."""

    run_block = spec.setdefault("run", {}) if isinstance(spec, dict) else {}
    if not isinstance(run_block, dict):
        run_block = {}
        spec["run"] = run_block

    csv_blk = run_block.setdefault("csv", {}) if isinstance(run_block, dict) else {}
    if not isinstance(csv_blk, dict):
        csv_blk = {}
        run_block["csv"] = csv_blk

    run_id_raw = str(csv_blk.get("run_id") or run_block.get("run_id") or "").strip()
    run_id = run_id_raw or uuid4().hex
    csv_blk["run_id"] = run_id

    raw_artifacts_dir = run_block.get("artifacts_dir")
    if isinstance(raw_artifacts_dir, (str, Path)) and str(raw_artifacts_dir).strip():
        artifacts_root = Path(raw_artifacts_dir)
        if not artifacts_root.is_absolute():
            artifacts_root = spec_path.parent / artifacts_root
    else:
        artifacts_root = spec_path.parent / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)

    run_dir = artifacts_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if not run_block.get("artifacts_dir"):
        run_block["artifacts_dir"] = str(run_dir)

    csv_blk.setdefault("enabled", True)
    csv_blk.setdefault("append", False)
    if not str(csv_blk.get("path", "")).strip():
        csv_blk["path"] = str(run_dir / "journal.csv")
    if args.seed is not None and "seed" not in csv_blk:
        csv_blk["seed"] = args.seed

    journal_blk = run_block.get("journal") if isinstance(run_block, dict) else None
    explain_cli = bool(getattr(args, "explain", False))
    explain_spec = bool(journal_blk.get("dsl_trace")) if isinstance(journal_blk, dict) else False
    explain_mode = explain_cli or explain_spec
    explain_source = "cli" if explain_cli else ("spec" if explain_spec else "default")

    decisions_writer = DecisionsTrace(run_dir) if explain_mode else None

    return run_dir, run_id, decisions_writer, explain_mode, explain_source


def _manifest_cli_flags(
    args: argparse.Namespace,
    *,
    explain_mode: bool,
    explain_source: str,
) -> Dict[str, Any]:
    flags: Dict[str, Any] = {}
    cli_flags_obj = getattr(args, "_cli_flags", None)
    if isinstance(cli_flags_obj, CLIFlags):
        flags.update({k: getattr(cli_flags_obj, k) for k in vars(cli_flags_obj)})
    flags.setdefault("strict", False)
    flags.setdefault("demo_fallbacks", False)
    flags.setdefault("embed_analytics", True)
    flags.setdefault("export", False)
    flags["explain"] = explain_mode
    flags["explain_source"] = explain_source or "default"
    flags.setdefault("human_summary", False)
    flags.setdefault("human_summary_source", "default")
    flags.setdefault("webhook_enabled", False)
    flags.setdefault("webhook_timeout", 2.0)
    flags.setdefault("webhook_url", None)
    flags.setdefault("webhook_url_source", "default")
    flags.setdefault("webhook_enabled_source", "default")
    flags.setdefault("evo_enabled", False)
    flags.setdefault("trial_tag", None)
    return flags


def _finalize_run_artifacts(
    run_dir: Path,
    run_id: str,
    spec_path: Path,
    args: argparse.Namespace,
    *,
    explain_mode: bool,
    explain_source: str,
    summary: Dict[str, Any],
    decisions_writer: Optional[DecisionsTrace],
) -> None:
    # Defensive coercion – earlier stages guarantee Path objects, but callers may still
    # pass strings when Specs embed serialized values (e.g., from manifests).  Treating
    # everything as a Path avoids "unsupported operand type(s) for /" issues when
    # composing child artifact paths.
    run_dir = Path(run_dir)
    spec_path = Path(spec_path)

    run_dir.mkdir(parents=True, exist_ok=True)

    if decisions_writer is not None:
        prev_rows = decisions_writer.rows_written
        decisions_writer.ensure_summary_row(summary)
        if prev_rows == 0:
            summary["decisions_rows"] = decisions_writer.rows_written
        else:
            summary.setdefault("decisions_rows", decisions_writer.rows_written)

    summary.setdefault("last_roll", summary.get("rolls"))

    summary_path = run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    journal_path = run_dir / "journal.csv"
    ensure_journal = False
    try:
        ensure_journal = not journal_path.exists() or journal_path.stat().st_size == 0
    except OSError:
        ensure_journal = True

    if ensure_journal:
        try:
            from .csv_journal import CSVJournal  # lazy import to avoid cycles

            journal = CSVJournal(
                str(journal_path),
                append=False,
                run_id=str(summary.get("run_id", run_id) or ""),
                seed=summary.get("seed"),
            )
            fallback_summary = {
                key: summary.get(key)
                for key in ("result", "rolls", "final_bankroll", "decisions_rows")
                if summary.get(key) is not None
            }
            snapshot = {
                "mode": summary.get("mode"),
                "units": summary.get("units"),
                "bankroll": summary.get("final_bankroll"),
            }
            journal.write_summary(fallback_summary, snapshot=snapshot)
        except Exception:
            journal_path.write_text(
                f"# journal_schema_version: {JOURNAL_SCHEMA_VERSION}\n",
                encoding="utf-8",
            )

    outputs = {
        "summary": "summary.json",
        "manifest": "manifest.json",
    }
    outputs["journal"] = "journal.csv"
    if decisions_writer is not None:
        outputs["decisions"] = "decisions.csv"

    cli_flags = _manifest_cli_flags(
        args,
        explain_mode=explain_mode,
        explain_source=explain_source,
    )

    manifest_payload = generate_manifest(
        str(spec_path),
        cli_flags,
        outputs,
        run_id=run_id,
    )

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _capture_control_surface_artifacts(
    spec: Dict[str, Any],
    spec_path: Path,
    args: argparse.Namespace,
    seed: Optional[int],
    rolls: int,
    bankroll: Optional[float],
    *,
    decisions_writer: Optional[DecisionsTrace] = None,
    explain_mode: bool = False,
) -> None:
    """Best-effort capture of journal/report/manifest artifacts."""

    try:
        from .controller import ControlStrategy
        from .csv_journal import CSVJournal
    except Exception:
        return

    spec_copy: Dict[str, Any] = copy.deepcopy(spec)
    if not isinstance(spec_copy, dict):
        return

    export_dir = Path("export")
    export_dir.mkdir(parents=True, exist_ok=True)

    run_blk = spec_copy.setdefault("run", {})
    if not isinstance(run_blk, dict):
        run_blk = {}
        spec_copy["run"] = run_blk

    csv_blk = run_blk.setdefault("csv", {}) if isinstance(run_blk, dict) else {}
    if not isinstance(csv_blk, dict):
        csv_blk = {}
        run_blk["csv"] = csv_blk
    csv_blk["enabled"] = True
    csv_blk["append"] = False
    configured_path = csv_blk.get("path")
    journal_path = (
        Path(configured_path)
        if isinstance(configured_path, str) and configured_path.strip()
        else export_dir / "journal.csv"
    )
    csv_blk["path"] = str(journal_path)
    if seed is not None:
        csv_blk["seed"] = seed

    run_id_raw = str(csv_blk.get("run_id") or "").strip()
    if not run_id_raw:
        trial_tag = getattr(args, "trial_tag", None)
        if isinstance(trial_tag, str) and trial_tag.strip():
            run_id_raw = trial_tag.strip()
        elif seed is not None:
            run_id_raw = f"baseline_{seed}"
        else:
            run_id_raw = "baseline_run"
        csv_blk["run_id"] = run_id_raw

    report_blk = run_blk.setdefault("report", {}) if isinstance(run_blk, dict) else {}
    if not isinstance(report_blk, dict):
        report_blk = {}
        run_blk["report"] = report_blk
    report_blk["path"] = str(export_dir / "report.json")
    report_blk["auto"] = True

    export_paths = {
        "journal": str(export_dir / "journal.csv"),
        "report": str(export_dir / "report.json"),
        "manifest": str(export_dir / "manifest.json"),
    }

    ctrl = ControlStrategy(
        spec_copy,
        spec_path=str(spec_path),
        cli_flags=getattr(args, "_cli_flags", None),
        explain=bool(explain_mode),
        decisions_writer=decisions_writer,
    )
    if seed is not None:
        try:
            ctrl._seed_value = seed  # type: ignore[attr-defined]
        except Exception:
            pass

    journal = ctrl._ensure_journal()
    if journal is None:
        journal = CSVJournal(
            export_paths["journal"],
            append=False,
            run_id=csv_blk.get("run_id"),
            seed=seed,
        )
        ctrl._journal = journal  # type: ignore[attr-defined]
        ctrl._journal_enabled = True  # type: ignore[attr-defined]
    else:
        journal.path = export_paths["journal"]
        if csv_blk.get("run_id"):
            journal.run_id = csv_blk.get("run_id")
        if seed is not None:
            journal.seed = seed

    summary_payload: Dict[str, Any] = {
        "rolls": rolls,
        "final_bankroll": float(bankroll) if bankroll is not None else None,
        "note": "phase4 baseline capture",
    }
    units_val = None
    try:
        units_val = ctrl._units_from_spec_or_state()  # type: ignore[attr-defined]
    except Exception:
        units_val = None
    snapshot = {
        "mode": getattr(ctrl, "mode", None),
        "units": units_val,
        "bankroll": float(bankroll) if bankroll is not None else None,
    }
    try:
        journal.write_summary(summary_payload, snapshot=snapshot)
    except Exception:
        pass

    try:
        ctrl.generate_report(
            report_path=export_paths["report"],
            spec_path=str(spec_path),
            cli_flags=getattr(args, "_cli_flags", None),
            export_paths=export_paths,
        )
    except Exception:
        pass


def run(args: argparse.Namespace) -> int:
    """
    Run path:
      1) Load & validate spec
      2) Compute rolls/seed
      3) Attach engine via EngineAdapter
      4) Drive the table
      5) Print result summary
    """
    # Load spec
    run_artifacts_dir: Optional[Path] = None
    run_id: str = ""
    decisions_writer: Optional[DecisionsTrace] = None
    explain_mode = False
    explain_source = "default"

    def _close_decisions_trace() -> None:
        nonlocal decisions_writer
        if decisions_writer is not None:
            try:
                decisions_writer.close()
            except Exception:
                pass
            decisions_writer = None

    spec_arg = getattr(args, "spec_override", None) or getattr(args, "spec", None)
    if not spec_arg:
        print("error: spec path is required", file=sys.stderr)
        _close_decisions_trace()
        return 2
    spec_path = Path(spec_arg)
    spec = _load_spec_file(spec_path)
    try:
        spec["_csc_spec_path"] = str(spec_path)
    except Exception:
        pass

    # Merge CLI flag overrides (before normalization/adapter usage)
    _merge_cli_run_flags(spec, args)

    risk_overrides: Dict[str, Any] = {}
    if not isinstance(spec, dict):
        spec = {}
    run_block = spec.get("run")
    if not isinstance(run_block, dict):
        run_block = {}
        spec["run"] = run_block
    run_artifacts_dir, run_id, decisions_writer, explain_mode, explain_source = (
        _prepare_run_artifacts(
            spec,
            spec_path,
            args,
        )
    )
    risk_block = run_block.get("risk")
    if not isinstance(risk_block, dict):
        risk_block = {}
        run_block["risk"] = risk_block

    policy_path = getattr(args, "risk_policy", None)
    if isinstance(policy_path, str) and policy_path and os.path.exists(policy_path):
        data: Dict[str, Any] | None = None
        try:
            if policy_path.lower().endswith((".yml", ".yaml")) and yaml is not None:
                with open(policy_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            else:
                with open(policy_path, "r", encoding="utf-8") as f:
                    try:
                        data = json.load(f)
                    except Exception:
                        data = None
        except Exception:
            data = None
        if isinstance(data, dict) and data:
            nested = data.get("run") if isinstance(data.get("run"), dict) else None
            source = (
                nested.get("risk")
                if isinstance(nested, dict) and isinstance(nested.get("risk"), dict)
                else data
            )
            if isinstance(source, dict):
                risk_block.update(source)
                risk_overrides["from_file"] = policy_path

    max_drawdown = getattr(args, "max_drawdown", None)
    if max_drawdown is not None:
        risk_block["max_drawdown_pct"] = float(max_drawdown)
        risk_overrides["max_drawdown_pct"] = float(max_drawdown)

    max_heat = getattr(args, "max_heat", None)
    if max_heat is not None:
        risk_block["max_heat"] = float(max_heat)
        risk_overrides["max_heat"] = float(max_heat)

    bet_caps_cli = getattr(args, "bet_cap", None) or []
    if bet_caps_cli:
        caps = risk_block.get("bet_caps")
        if not isinstance(caps, dict):
            caps = {}
        for cap in bet_caps_cli:
            if not isinstance(cap, str) or ":" not in cap:
                continue
            key, raw_value = cap.split(":", 1)
            key = key.strip()
            raw_value = raw_value.strip()
            if not key:
                continue
            try:
                value = float(raw_value)
            except ValueError:
                continue
            caps[key] = value
            risk_overrides[f"bet_cap_{key}"] = value
        if caps:
            risk_block["bet_caps"] = caps

    recovery_mode = getattr(args, "recovery", None)
    if recovery_mode:
        mode = (
            "none"
            if recovery_mode == "none"
            else ("flat_recovery" if recovery_mode == "flat" else "step_recovery")
        )
        risk_block["recovery"] = {"enabled": mode != "none", "mode": mode}
        risk_overrides["recovery_mode"] = mode

    if getattr(args, "no_policy_enforce", False):
        policy_block = run_block.setdefault("policy", {})
        policy_block["enforce"] = False
    if getattr(args, "policy_report", False):
        policy_block = run_block.setdefault("policy", {})
        policy_block["report"] = True

    if getattr(args, "no_stop_on_bankrupt", False):
        run_block["stop_on_bankrupt"] = False
    if getattr(args, "no_stop_on_unactionable", False):
        run_block["stop_on_unactionable"] = False

    # spec-level runtime
    spec_run_raw = spec.get("run")
    spec_run = spec_run_raw if isinstance(spec_run_raw, dict) else {}
    rolls = int(args.rolls) if args.rolls is not None else int(spec_run.get("rolls", 1000))
    seed = args.seed if args.seed is not None else spec_run.get("seed")

    # Flags (merged with spec)
    demo_fallbacks = normalize_demo_fallbacks(spec_run)
    strict_norm, strict_ok = coerce_flag(spec_run.get("strict"), default=STRICT_DEFAULT)
    strict = bool(strict_norm) if strict_ok and strict_norm is not None else STRICT_DEFAULT
    csv_blk = spec_run.get("csv") if isinstance(spec_run.get("csv"), dict) else {}
    embed_norm, embed_ok = coerce_flag(
        (csv_blk or {}).get("embed_analytics"), default=EMBED_ANALYTICS_DEFAULT
    )
    embed_analytics = (
        bool(embed_norm) if embed_ok and embed_norm is not None else EMBED_ANALYTICS_DEFAULT
    )
    rng_audit = bool(getattr(args, "rng_audit", False))
    if log.isEnabledFor(logging.DEBUG):
        log.debug(
            "CLI run flags: demo_fallbacks=%s strict=%s embed_analytics=%s rng_audit=%s",
            demo_fallbacks,
            strict,
            embed_analytics,
            rng_audit,
        )

    # Validate (can be bypassed by workflow env)
    if os.environ.get("CSC_SKIP_VALIDATE", "0").lower() not in ("1", "true", "yes"):
        ok, hard_errs, soft_warns = _lazy_validate_spec(spec)
        if not ok or hard_errs:
            print("failed validation:", file=sys.stderr)
            for e in hard_errs:
                print(f"- {e}", file=sys.stderr)
            _close_decisions_trace()
            return 2
        for w in soft_warns:
            log.warning("spec warning: %s", w)

    print(f"validation_engine: {VALIDATION_ENGINE_VERSION}")

    info = _csv_journal_info(spec)
    if info:
        print(info)

    # Seed RNGs under our control
    seed_int = None
    if seed is not None:
        try:
            seed_int = int(seed)
        except Exception:
            seed_int = None
    _smart_seed(seed_int)
    _reseed_engine(seed_int)

    # Attach engine
    try:
        from crapssim_control.engine_adapter import EngineAdapter, resolve_engine_adapter  # lazy

        adapter_cls = None
        reason = None
        if "EngineAdapter" in locals() and not inspect.isabstract(EngineAdapter):
            adapter_cls = EngineAdapter
        else:
            adapter_cls, reason = resolve_engine_adapter()

        if adapter_cls is None:
            raise RuntimeError(reason or "engine adapter scaffolding not connected")

        adapter = adapter_cls()
        if not hasattr(adapter, "attach"):
            raise RuntimeError("engine adapter missing attach() implementation")
        attach_result = adapter.attach(spec)
        risk_policy = load_risk_policy(spec)
        adapter._risk_policy = risk_policy  # type: ignore[attr-defined]
        adapter._policy_engine = PolicyEngine(risk_policy)  # type: ignore[attr-defined]
        adapter._policy_opts = get_policy_options(spec)  # type: ignore[attr-defined]
        adapter._stop_opts = get_stop_options(spec)  # type: ignore[attr-defined]
        adapter._policy_overrides = dict(risk_overrides)
        if risk_overrides:
            try:
                print(f"Risk policy active: {json.dumps(risk_overrides, separators=(',',':'))}")
            except Exception:
                print("Risk policy active: overrides applied")
        table = attach_result.table
        # CRITICAL: seed the actual dice/rng instance now that it exists
        _force_seed_on_table(table, seed_int)

        if rng_audit:
            # best-effort introspection only (stdout, ignored by RESULT grep)
            try:
                attrs = {k: bool(getattr(table, k, None)) for k in ("dice", "_dice", "rng", "_rng")}
                print(f"[rng] seed={seed_int} table_attrs={attrs}")
            except Exception:
                pass

        log.debug("attach meta: %s", getattr(attach_result, "meta", {}))
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("DEBUG attach_result:", getattr(attach_result, "meta", {}))
    except Exception as e:
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("\n--- CSC DEBUG TRACEBACK (attach) ---", flush=True)
            traceback.print_exc()
            print("--- END CSC DEBUG ---\n", flush=True)
        _close_decisions_trace()
        return _engine_unavailable(e)

    # Drive the table
    log.info("Starting run: rolls=%s seed=%s", rolls, seed_int)
    ok, used = _run_table_rolls(table, rolls)
    if not ok:
        msg = f"Could not run {rolls} rolls. {used}."
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("\n--- CSC DEBUG: run failure ---", msg, "\n", flush=True)
        _close_decisions_trace()
        return _engine_unavailable(msg)

    # Summarize
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

    summary_payload: Dict[str, Any] = {
        "run_id": run_id,
        "spec": str(spec_path),
        "rolls": rolls,
        "seed": seed_int,
        "final_bankroll": float(bankroll) if bankroll is not None else None,
        "artifacts_dir": str(run_artifacts_dir) if run_artifacts_dir is not None else None,
        "decisions_rows": decisions_writer.rows_written if decisions_writer is not None else 0,
        "result": "ok",
    }

    run_config = spec_run
    run_config["dsl"] = bool(getattr(args, "dsl", False))
    run_config["dsl_once_per_window"] = bool(getattr(args, "dsl_once_per_window", True))
    run_config["dsl_verbose_journal"] = bool(getattr(args, "dsl_verbose_journal", False))
    print(
        "Schema versions → "
        f"journal={run_config.get('journal_schema_version', JOURNAL_SCHEMA_VERSION)} "
        f"summary={run_config.get('summary_schema_version', SUMMARY_SCHEMA_VERSION)}"
    )
    print(f"CSC version → {CSC_VERSION}")

    # Optional CSV export
    if getattr(args, "export", None):
        try:
            _write_csv_summary(
                args.export,
                {
                    "spec": str(spec_path),
                    "rolls": rolls,
                    "final_bankroll": float(bankroll) if bankroll is not None else None,
                    "seed": seed_int,
                    "note": getattr(
                        getattr(attach_result, "meta", {}), "get", lambda _k, _d=None: _d
                    )("mode", ""),
                },
            )
            log.info("Exported summary CSV → %s", args.export)
            if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
                print(f"[CSV] wrote summary to {args.export}")
        except Exception as e:
            print(f"warn: export failed: {e}", file=sys.stderr)

    try:
        _capture_control_surface_artifacts(
            spec,
            spec_path,
            args,
            seed_int,
            rolls,
            float(bankroll) if bankroll is not None else None,
            decisions_writer=decisions_writer,
            explain_mode=explain_mode,
        )
    except Exception:
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("warn: control-surface capture failed", file=sys.stderr)
        log.debug("control surface capture failed", exc_info=True)

    try:
        _finalize_run_artifacts(
            run_artifacts_dir or (spec_path.parent / "artifacts" / run_id),
            run_id,
            spec_path,
            args,
            explain_mode=explain_mode,
            explain_source=explain_source,
            summary=summary_payload,
            decisions_writer=decisions_writer,
        )
    except Exception:
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("warn: finalize artifacts failed", file=sys.stderr)
        log.debug("finalize run artifacts failed", exc_info=True)

    _close_decisions_trace()
    return 0


# ------------------------------ Parser/Main --------------------------------- #


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
    try:
        return run(args)
    except Exception:
        if os.environ.get("CSC_DEBUG", "0").lower() in ("1", "true", "yes"):
            print("\n--- CSC DEBUG TRACEBACK ---", flush=True)
            traceback.print_exc()
            print("--- END CSC DEBUG ---\n", flush=True)
        raise


def _cmd_summarize(args: argparse.Namespace) -> int:
    return summarize_run(args.artifacts, human=bool(getattr(args, "human", False)))


def _cmd_init(args: argparse.Namespace) -> int:
    init_run(args.target_dir)
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    try:
        result = doctor_run(args.spec)
    except SystemExit as exc:  # pragma: no cover - passthrough for doctor exit semantics
        code = exc.code if isinstance(exc.code, int) else 0
        return code
    if result is None:
        return 0
    return int(result)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crapssim-ctl",
        description="Crapssim Control - validate specs and run simulations",
    )
    parser.epilog = "Use `run --explain` to emit decisions.csv alongside run artifacts."
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase verbosity (use -vv for debug)",
    )
    parser.add_argument(
        "--lint-rules",
        dest="lint_rules",
        help="Validate rule spec JSON or YAML file.",
    )
    parser.add_argument(
        "--expand-macros",
        dest="expand_macros",
        help="Expand macros into full rule JSON.",
    )
    parser.add_argument(
        "--macros",
        dest="macros",
        default="templates/core_macros.yaml",
        help="Path to macro YAML file.",
    )

    sub = parser.add_subparsers(dest="subcommand", required=False)

    # summarize
    p_sum = sub.add_parser("summarize", help="Summarize run artifacts")
    p_sum.add_argument("--artifacts", required=True, help="Path to artifacts directory")
    p_sum.add_argument("--human", action="store_true", help="Generate human-readable report.md")
    p_sum.set_defaults(func=_cmd_summarize)

    # init
    p_init = sub.add_parser("init", help="Scaffold a CSC skeleton project")
    p_init.add_argument("target_dir", help="Target directory to initialize")
    p_init.set_defaults(func=_cmd_init)

    # doctor
    p_doc = sub.add_parser("doctor", help="Sanity check a CSC spec file")
    p_doc.add_argument(
        "--spec", dest="spec", default=None, help="Path to spec.json (default: spec.json)"
    )
    p_doc.set_defaults(func=_cmd_doctor)

    # validate
    p_val = sub.add_parser("validate", help="Validate a strategy spec (JSON or YAML)")
    p_val.add_argument("spec", help="Path to spec file")
    p_val.add_argument(
        "--hot-table",
        action="store_true",
        dest="hot_table",
        help='Plan with "hot table" defaults (no behavior change yet)',
    )
    p_val.add_argument(
        "--guardrails",
        action="store_true",
        help="Print Guardrail planning notes (strict-mode context; Advisories remain default).",
    )
    p_val.set_defaults(func=_cmd_validate)

    # run
    p_run = sub.add_parser("run", help="Run a simulation for a given spec")
    p_run.add_argument("spec", nargs="?", help="Path to spec file")
    p_run.add_argument("--spec", dest="spec_override", metavar="SPEC", help="Path to spec file")
    p_run.add_argument("--rolls", type=int, help="Number of rolls (overrides spec)")
    p_run.add_argument("--seed", type=int, help="Seed RNG for reproducibility")
    p_run.add_argument(
        "--export",
        nargs="?",
        const="export/summary.csv",
        type=str,
        help="Path to CSV summary export (optional; defaults to export/summary.csv)",
    )
    p_run.add_argument(
        "--dsl",
        action="store_true",
        help="Enable DSL rule evaluation (behavior.rules)",
    )
    p_run.add_argument(
        "--dsl-once-per-window",
        action="store_true",
        default=True,
        help="Stop after first applied rule per window (MVP)",
    )
    p_run.add_argument(
        "--dsl-verbose-journal",
        action="store_true",
        default=False,
        help="Journal non-triggering evaluations",
    )
    # runtime flag overrides
    p_run.add_argument(
        "--demo-fallbacks",
        action="store_true",
        help=(
            "Enable demo helper bets for this run (default OFF). Leave unset or set "
            "run.demo_fallbacks=false to keep them disabled."
        ),
    )
    p_run.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Enable Guardrails (strict validation) for this run. Advisories are the default; "
            "use run.strict=false to remain advisory."
        ),
    )
    p_run.add_argument(
        "--max-drawdown",
        type=float,
        help="Maximum drawdown percentage (0-100).",
    )
    p_run.add_argument(
        "--max-heat",
        type=float,
        help="Maximum total exposure allowed.",
    )
    p_run.add_argument(
        "--bet-cap",
        action="append",
        help="Override cap for a bet type, format: bet:amount (repeatable).",
    )
    p_run.add_argument(
        "--recovery",
        choices=["none", "flat", "step"],
        help="Set recovery mode.",
    )
    p_run.add_argument(
        "--risk-policy",
        type=str,
        help="Path to YAML/JSON risk policy file.",
    )
    p_run.add_argument(
        "--no-policy-enforce",
        action="store_true",
        help="Disable enforcement (policy logs only).",
    )
    p_run.add_argument(
        "--policy-report",
        action="store_true",
        help="Include policy stats in summary.",
    )
    p_run.add_argument(
        "--no-stop-on-bankrupt",
        action="store_true",
        help="Disable early termination on bankroll exhaustion.",
    )
    p_run.add_argument(
        "--no-stop-on-unactionable",
        action="store_true",
        help="Disable early termination when no legal bet is possible.",
    )
    p_run.add_argument(
        "--no-embed-analytics",
        action="store_true",
        dest="no_embed_analytics",
        help=(
            "Disable analytics embedding for this run (default ON). Leave unset or set "
            "run.csv.embed_analytics=true to keep analytics columns."
        ),
    )
    p_run.add_argument(
        "--evo-enabled",
        action="store_true",
        help="Enable EvoBridge scaffold hooks for this run.",
    )
    p_run.add_argument(
        "--trial-tag",
        type=str,
        default=None,
        help="Assign an Evo trial tag for downstream cohort tracking.",
    )
    p_run.add_argument(
        "--webhook-url",
        type=str,
        default=None,
        help=("POST lifecycle events to this webhook endpoint (disabled unless URL provided)."),
    )
    p_run.add_argument(
        "--webhook-timeout",
        type=float,
        default=2.0,
        help="Timeout in seconds for outbound webhook POSTs (default 2.0).",
    )
    p_run.add_argument(
        "--no-webhook",
        action="store_true",
        help="Disable outbound webhook emission even if a URL is configured.",
    )
    p_run.add_argument(
        "--rng-audit",
        action="store_true",
        help="(scaffold) Print RNG inspection info (does not affect results).",
    )
    p_run.add_argument(
        "--explain",
        action="store_true",
        help="Print rule decisions and write artifacts/<run_id>/decisions.csv",
    )
    p_run.set_defaults(func=_cmd_run)

    # dsl helpers
    p_dsl = sub.add_parser("dsl", help="DSL authoring utilities (new, validate, list)")
    p_dsl.add_argument("action", help="new|validate|list")
    p_dsl.add_argument("args", nargs="*", help="template args or file")

    # journal summarize
    p_j = sub.add_parser("journal", help="CSV journal utilities")
    p_j_sub = p_j.add_subparsers(dest="journal_cmd", required=True)
    p_js = p_j_sub.add_parser("summarize", help="Summarize a per-event journal CSV")
    p_js.add_argument("journal", help="Path to journal.csv")
    p_js.add_argument("--out", type=str, default=None, help="Write summary CSV to this path")
    p_js.add_argument("--append", action="store_true", help="Append to --out if it exists")
    p_js.add_argument(
        "--no-group", action="store_true", help="Do not group by run_id; summarize whole file"
    )
    p_js.set_defaults(func=_cmd_journal_summarize)

    return parser


def main(argv: List[str] | None = None) -> int:
    _scrub_inert_env()  # keep CSC_FORCE_SEED intact
    if argv is None:
        argv = sys.argv[1:]
    cli_flags = parse_flags(argv)
    parser = _build_parser()
    args = parser.parse_args(argv)
    setattr(args, "_cli_flags", cli_flags)
    setup_logging(args.verbose)
    handled = False
    builder: RuleBuilder | None = None

    if getattr(args, "lint_rules", None) or getattr(args, "expand_macros", None):
        builder = RuleBuilder(macros_file=args.macros)

    if getattr(args, "lint_rules", None):
        assert builder is not None
        rules = builder.expand(args.lint_rules)
        warnings = builder.lint(rules)
        if warnings:
            for warn in warnings:
                print(f"Lint: {warn}")
        else:
            print("No issues found.")
        handled = True

    if getattr(args, "expand_macros", None):
        assert builder is not None
        rules = builder.expand(args.expand_macros)
        builder.save(rules, "expanded_rules.json")
        print("Expanded to expanded_rules.json")
        handled = True

    if handled and not getattr(args, "subcommand", None):
        return 0

    if getattr(args, "subcommand", None) == "dsl":
        from crapssim_control import dsl_helpers

        return dsl_helpers.cli_entry(["dsl", args.action, *list(args.args)])

    if not hasattr(args, "func") or args.func is None:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
