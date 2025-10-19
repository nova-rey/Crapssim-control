#!/usr/bin/env python3
"""Validate deterministic replay for the Phase 6 baseline."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from crapssim_control.controller import ControlStrategy  # noqa: E402
from crapssim_control.spec_loader import load_spec_file  # noqa: E402
from scripts.phase6_baseline_utils import generate_event_sequence, iter_event_dicts  # noqa: E402

FINAL_DIR = ROOT / "baselines" / "phase6" / "final"
REPLAY_DIR = ROOT / "baselines" / "phase6" / "replay_validation"
LIVE_COMMAND_TAPE = FINAL_DIR / "command_tape.jsonl"
REPORT_PATH = REPLAY_DIR / "report.json"
MANIFEST_PATH = REPLAY_DIR / "manifest.json"
JOURNAL_PATH = REPLAY_DIR / "decision_journal.jsonl"
EXPORT_DIR = ROOT / "export"
ROOT_JOURNAL_PATH = ROOT / "decision_journal.jsonl"
CSV_JOURNAL_PATH = EXPORT_DIR / "journal_replay.csv"
DEFAULT_SEED = 13579
RUN_ID = "phase6-external-replay"


def _ensure_seed() -> int:
    seed_text = os.environ.get("CSC_SEED")
    if seed_text is None:
        os.environ["CSC_SEED"] = str(DEFAULT_SEED)
        return DEFAULT_SEED
    try:
        return int(seed_text)
    except ValueError:
        os.environ["CSC_SEED"] = str(DEFAULT_SEED)
        return DEFAULT_SEED


def _prepare_directories() -> None:
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (REPORT_PATH, MANIFEST_PATH, JOURNAL_PATH):
        if path.exists():
            path.unlink()
    if ROOT_JOURNAL_PATH.exists():
        ROOT_JOURNAL_PATH.unlink()


def _replay_spec(seed: int) -> Dict[str, object]:
    spec_path = ROOT / "examples" / "internal_brain_demo" / "spec.yaml"
    spec, _ = load_spec_file(spec_path)
    run_cfg: Dict[str, object] = dict(spec.get("run", {}))
    run_cfg["seed"] = seed
    run_cfg["rolls"] = 60

    csv_cfg = dict(run_cfg.get("csv", {}))
    csv_cfg.update({
        "enabled": True,
        "path": str(CSV_JOURNAL_PATH),
        "append": False,
        "run_id": RUN_ID,
    })
    run_cfg["csv"] = csv_cfg

    report_cfg = dict(run_cfg.get("report", {}))
    report_cfg.update({"path": str(REPORT_PATH), "auto": True})
    run_cfg["report"] = report_cfg

    external_cfg = dict(run_cfg.get("external", {}))
    external_cfg.update({
        "mode": "replay",
        "tape_path": str(LIVE_COMMAND_TAPE),
    })
    run_cfg["external"] = external_cfg

    spec["run"] = run_cfg
    return spec


def _drive_controller(ctrl: ControlStrategy, events: Iterable[Dict[str, object]]) -> None:
    for event in events:
        ctrl.handle_event(event, current_bets={})


def main() -> int:
    if not LIVE_COMMAND_TAPE.exists():
        raise SystemExit("live command tape missing; run phase6_baseline_live.py first")

    seed = _ensure_seed()
    _prepare_directories()
    spec = _replay_spec(seed)

    controller = ControlStrategy(spec, spec_path=None)
    controller.journal.path = str(JOURNAL_PATH)
    events = iter_event_dicts(generate_event_sequence(seed))
    _drive_controller(controller, events)

    controller.generate_report(
        report_path=str(REPORT_PATH),
        export_paths={
            "report": str(REPORT_PATH),
            "manifest": str(MANIFEST_PATH),
            "journal": str(JOURNAL_PATH),
            "command_tape": str(LIVE_COMMAND_TAPE),
        },
    )

    journal_source = Path(getattr(getattr(controller, "journal", None), "path", JOURNAL_PATH))
    if not journal_source.exists():
        journal_candidates = [
            REPORT_PATH.parent / "decision_journal.jsonl",
            ROOT_JOURNAL_PATH,
        ]
        for candidate in journal_candidates:
            if candidate.exists():
                journal_source = candidate
                break
    if journal_source.exists() and journal_source != JOURNAL_PATH:
        JOURNAL_PATH.write_text(journal_source.read_text(encoding="utf-8"), encoding="utf-8")

    report = json.loads(REPORT_PATH.read_text(encoding="utf-8")) if REPORT_PATH.exists() else {}
    if report:
        identity = report.setdefault("identity", {})
        identity.setdefault("run_id", RUN_ID)
        identity["seed"] = seed
        report["run_id"] = RUN_ID
        report["manifest_path"] = str(MANIFEST_PATH)

        metadata = report.setdefault("metadata", {})
        artifacts = metadata.setdefault("artifacts", {})
        artifacts.update(
            {
                "journal": str(JOURNAL_PATH),
                "journal_csv": str(CSV_JOURNAL_PATH),
                "command_tape": str(LIVE_COMMAND_TAPE),
                "manifest": str(MANIFEST_PATH),
                "report": str(REPORT_PATH),
            }
        )

        live_report_path = FINAL_DIR / "report.json"
        if live_report_path.exists():
            try:
                live_report = json.loads(live_report_path.read_text(encoding="utf-8"))
            except Exception:
                live_report = {}
            live_limits = (
                live_report.get("metadata", {})
                .get("limits", {})
                if isinstance(live_report, dict)
                else {}
            )
            if isinstance(live_limits, dict) and live_limits:
                metadata.setdefault("limits", {}).update(live_limits)

        run_flags = metadata.setdefault("run_flags", {})
        run_flags["webhook_enabled"] = False
        run_flags["webhook_enabled_source"] = "replay"
        run_flags.setdefault("webhook_url_masked", True)
        run_flags["webhook_url_source"] = "replay"
        run_flags["external_mode"] = "replay"
        run_flags["external_mode_source"] = "spec"
        sources = run_flags.setdefault("sources", {})
        sources["external_mode"] = "spec"
        sources["webhook_enabled"] = "replay"

        values = run_flags.setdefault("values", {})
        values.setdefault("demo_fallbacks", False)
        values.setdefault("embed_analytics", True)
        values.setdefault("strict", False)

        csv_section = report.setdefault("csv", {})
        csv_section["path"] = str(CSV_JOURNAL_PATH)

        source_files = report.setdefault("source_files", {})
        source_files["csv"] = str(CSV_JOURNAL_PATH)
        source_files["decision_journal"] = str(JOURNAL_PATH)

        REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    manifest.setdefault("run_id", RUN_ID)
    manifest["spec_file"] = str((ROOT / "examples" / "internal_brain_demo" / "spec.yaml").relative_to(ROOT))
    manifest.setdefault("cli_flags", {})
    manifest["cli_flags"].update(
        {
            "demo_fallbacks": False,
            "strict": False,
            "embed_analytics": True,
            "export": False,
            "webhook_enabled": False,
            "webhook_timeout": 2.0,
            "webhook_url": None,
            "webhook_url_source": "replay",
            "webhook_enabled_source": "replay",
            "external_mode": "replay",
            "external_mode_source": "spec",
        }
    )
    manifest.setdefault("output_paths", {})
    manifest["output_paths"].update(
        {
            "journal": str(JOURNAL_PATH),
            "journal_csv": str(CSV_JOURNAL_PATH),
            "report": str(REPORT_PATH),
            "manifest": str(MANIFEST_PATH),
            "command_tape": str(LIVE_COMMAND_TAPE),
        }
    )
    manifest.setdefault("integrations", {})
    webhook_meta = manifest["integrations"].setdefault("webhook", {})
    webhook_meta.update({"enabled": False, "url_present": False, "timeout": 2.0})
    manifest.setdefault("schema", {})
    manifest["schema"].setdefault("journal", report.get("journal_schema_version", "1.2"))
    manifest["schema"].setdefault("summary", report.get("summary_schema_version", "1.2"))
    manifest.setdefault("engine_version", report.get("metadata", {}).get("engine", {}).get("version", "CrapsSim-Control"))
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("Replay captured →", REPLAY_DIR)
    return 0


if __name__ == "__main__":  # pragma: no cover - integration entry point
    raise SystemExit(main())
