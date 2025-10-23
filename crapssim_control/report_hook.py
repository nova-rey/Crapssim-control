from __future__ import annotations
import json
import os
from typing import Any, Dict, Optional

from .reporting import parse_journal_csv, compute_report_v2


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def maybe_enrich_report(artifacts_dir: str) -> bool:
    """
    If journal.csv and (optionally) report.json exist in artifacts_dir, compute Reports v2,
    merge identity/version fields (engine/csc/run_id) from existing manifest/report,
    and write back report.json with expanded metrics. Returns True if enriched.
    """
    if not artifacts_dir or not os.path.isdir(artifacts_dir):
        return False

    journal_path = os.path.join(artifacts_dir, "journal.csv")
    report_path = os.path.join(artifacts_dir, "report.json")
    manifest_path = os.path.join(artifacts_dir, "manifest.json")

    if not os.path.isfile(journal_path):
        return False

    rows = parse_journal_csv(journal_path)
    prior_report = _load_json(report_path) or {}
    manifest = _load_json(manifest_path) or {}

    identity_overrides: Dict[str, Any] = {}
    run_id = prior_report.get("identity", {}).get("run_id") or manifest.get("run_id")
    if run_id:
        identity_overrides["run_id"] = run_id
    for k in ("engine_version", "csc_version"):
        v = prior_report.get("identity", {}).get(k) or manifest.get(k)
        if v:
            identity_overrides[k] = v

    bankroll_start = None
    if "summary" in prior_report and "bankroll_start" in prior_report["summary"]:
        bankroll_start = prior_report["summary"]["bankroll_start"]

    bet_digest = None
    if "by_bet_family" in prior_report and isinstance(prior_report["by_bet_family"], dict):
        raw = prior_report["by_bet_family"].get("digest")
        if isinstance(raw, list):
            bet_digest = raw

    v2 = compute_report_v2(
        rows,
        bankroll_start=bankroll_start,
        bet_family_digest=bet_digest,
        identity_overrides=identity_overrides,
    )

    report: Dict[str, Any] = {}
    if isinstance(prior_report, dict):
        report = dict(prior_report)

    identity_existing = report.get("identity") if isinstance(report.get("identity"), dict) else {}
    identity = dict(identity_existing)
    identity.update(v2.get("identity", {}))
    report["identity"] = identity

    for field in ("journal_schema_version", "summary_schema_version", "report_schema_version"):
        if identity.get(field):
            report[field] = identity[field]
        elif v2.get("identity", {}).get(field):
            report[field] = v2["identity"][field]

    summary_existing = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    summary = dict(summary_existing)
    for key, value in v2.get("summary", {}).items():
        if value is not None or key not in summary:
            summary[key] = value
    report["summary"] = summary

    for section in ("point_cycle", "risk_series", "by_bet_family"):
        existing = report.get(section) if isinstance(report.get(section), dict) else {}
        merged = dict(existing)
        new_block = v2.get(section, {})
        if isinstance(new_block, dict):
            for key, value in new_block.items():
                if value is not None or key not in merged:
                    merged[key] = value
        report[section] = merged

    flags_existing = report.get("flags") if isinstance(report.get("flags"), dict) else {}
    flags = dict(v2.get("flags", {}))
    flags.update(flags_existing)
    report["flags"] = flags

    _write_json(report_path, report)
    return True
