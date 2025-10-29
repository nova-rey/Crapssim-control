#!/usr/bin/env python3
"""Capture the seeded Phase 6 external-control baseline (live mode)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Iterable
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from crapssim_control.controller import ControlStrategy  # noqa: E402
from crapssim_control.simulators import NodeRedSimulator  # noqa: E402
from crapssim_control.spec_loader import load_spec_file  # noqa: E402
from scripts.phase6_baseline_utils import generate_event_sequence, iter_event_dicts  # noqa: E402

FINAL_DIR = ROOT / "baselines" / "phase6" / "final"
COMMAND_TAPE_PATH = FINAL_DIR / "command_tape.jsonl"
REPORT_PATH = FINAL_DIR / "report.json"
MANIFEST_PATH = FINAL_DIR / "manifest.json"
JOURNAL_PATH = FINAL_DIR / "decision_journal.jsonl"
DIAGNOSTICS_PATH = FINAL_DIR / "diagnostics.json"
EXPORT_DIR = ROOT / "export"
ROOT_JOURNAL_PATH = ROOT / "decision_journal.jsonl"
CSV_JOURNAL_PATH = EXPORT_DIR / "journal.csv"
WEBHOOK_URL = "http://127.0.0.1:1880/webhook"
DEFAULT_SEED = 13579
RUN_ID = "phase6-external-live"


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
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (COMMAND_TAPE_PATH, REPORT_PATH, MANIFEST_PATH, JOURNAL_PATH, DIAGNOSTICS_PATH):
        if path.exists():
            path.unlink()
    if ROOT_JOURNAL_PATH.exists():
        ROOT_JOURNAL_PATH.unlink()


def _baseline_spec(seed: int) -> Dict[str, object]:
    spec_path = ROOT / "examples" / "internal_brain_demo" / "spec.yaml"
    spec, _ = load_spec_file(spec_path)
    run_cfg: Dict[str, object] = dict(spec.get("run", {}))
    run_cfg["seed"] = seed
    run_cfg["rolls"] = 60

    csv_cfg = dict(run_cfg.get("csv", {}))
    csv_cfg.update(
        {
            "enabled": True,
            "path": str(CSV_JOURNAL_PATH),
            "append": False,
            "run_id": RUN_ID,
        }
    )
    run_cfg["csv"] = csv_cfg

    report_cfg = dict(run_cfg.get("report", {}))
    report_cfg.update({"path": str(REPORT_PATH), "auto": True})
    run_cfg["report"] = report_cfg

    webhook_cfg = dict(run_cfg.get("webhooks", {}))
    webhook_cfg.update(
        {
            "enabled": True,
            "targets": [WEBHOOK_URL],
            "timeout": 2.0,
        }
    )
    run_cfg["webhooks"] = webhook_cfg

    http_cfg = dict(run_cfg.get("http_commands", {}))
    http_cfg.update({"enabled": True})
    run_cfg["http_commands"] = http_cfg

    external_cfg = dict(run_cfg.get("external", {}))
    external_cfg.update(
        {
            "mode": "live",
            "tape_path": str(COMMAND_TAPE_PATH),
        }
    )
    run_cfg["external"] = external_cfg

    spec["run"] = run_cfg
    return spec


def _fetch_json(url: str) -> Dict[str, object]:
    try:
        with urlrequest.urlopen(url, timeout=2.0) as resp:
            body = resp.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            return {"status": resp.getcode(), "body": payload}
    except Exception as exc:
        return {"error": str(exc)}


def _drive_controller(ctrl: ControlStrategy, events: Iterable[Dict[str, object]]) -> None:
    time.sleep(0.5)
    for event in events:
        ctrl.handle_event(event, current_bets={})
        bankroll_after = event.get("bankroll_after")
        pause = 0.2
        try:
            bankroll_val = float(bankroll_after) if bankroll_after is not None else None
        except Exception:
            bankroll_val = None
        if bankroll_val is not None and bankroll_val < 900:
            pause = 0.5
        time.sleep(pause)


def main() -> int:
    seed = _ensure_seed()
    _prepare_directories()
    spec = _baseline_spec(seed)

    simulator = NodeRedSimulator()
    simulator.start()

    controller = ControlStrategy(spec, spec_path=None)
    controller.journal.path = str(JOURNAL_PATH)
    events = iter_event_dicts(generate_event_sequence(seed))

    try:
        _drive_controller(controller, events)
        controller.generate_report(
            report_path=str(REPORT_PATH),
            export_paths={
                "report": str(REPORT_PATH),
                "manifest": str(MANIFEST_PATH),
                "journal": str(JOURNAL_PATH),
                "command_tape": str(COMMAND_TAPE_PATH),
            },
        )
    finally:
        simulator.stop()

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
                "command_tape": str(COMMAND_TAPE_PATH),
                "manifest": str(MANIFEST_PATH),
                "report": str(REPORT_PATH),
            }
        )

        run_flags = metadata.setdefault("run_flags", {})
        run_flags["webhook_enabled"] = True
        run_flags["webhook_enabled_source"] = "spec"
        run_flags.setdefault("webhook_url_masked", True)
        run_flags["webhook_url_source"] = "spec"
        run_flags["external_mode"] = "live"
        run_flags["external_mode_source"] = "spec"
        sources = run_flags.setdefault("sources", {})
        sources["webhook_enabled"] = "spec"
        sources["external_mode"] = "spec"

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

    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    else:
        manifest = {}
    manifest.setdefault("run_id", RUN_ID)
    manifest["spec_file"] = str(
        (ROOT / "examples" / "internal_brain_demo" / "spec.yaml").relative_to(ROOT)
    )
    manifest.setdefault("cli_flags", {})
    manifest["cli_flags"].update(
        {
            "demo_fallbacks": False,
            "strict": False,
            "embed_analytics": True,
            "export": False,
            "webhook_enabled": True,
            "webhook_timeout": 2.0,
            "webhook_url": WEBHOOK_URL,
            "webhook_url_source": "spec",
            "webhook_enabled_source": "spec",
            "external_mode": "live",
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
            "command_tape": str(COMMAND_TAPE_PATH),
        }
    )
    manifest.setdefault("integrations", {})
    webhook_meta = manifest["integrations"].setdefault("webhook", {})
    webhook_meta.update({"enabled": True, "url_present": True, "timeout": 2.0})
    manifest.setdefault("schema", {})
    manifest["schema"].setdefault("journal", report.get("journal_schema_version", "1.2"))
    manifest["schema"].setdefault("summary", report.get("summary_schema_version", "1.2"))
    manifest.setdefault(
        "engine_version",
        report.get("metadata", {}).get("engine", {}).get("version", "CrapsSim-Control"),
    )
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    diagnostics = {
        "health": _fetch_json("http://127.0.0.1:8089/health"),
        "run_id": _fetch_json("http://127.0.0.1:8089/run_id"),
        "version": _fetch_json("http://127.0.0.1:8089/version"),
    }
    DIAGNOSTICS_PATH.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")

    print("Baseline captured →", FINAL_DIR)
    return 0


if __name__ == "__main__":  # pragma: no cover - integration entry point
    raise SystemExit(main())
