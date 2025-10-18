"""
Run Manifest generator: captures run metadata, CLI flags, schema versions, and outputs.
"""
from uuid import uuid4
from datetime import datetime
from .schemas import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION


def iso_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def generate_manifest(
    spec_file: str,
    cli_flags: dict,
    outputs: dict,
    *,
    engine_version: str = None,
    run_id: str | None = None,
):
    manifest_run_id = str(run_id) if run_id else str(uuid4())
    return {
        "run_id": manifest_run_id,
        "timestamp": iso_now(),
        "spec_file": spec_file,
        "cli_flags": cli_flags,
        "schema": {
            "journal": JOURNAL_SCHEMA_VERSION,
            "summary": SUMMARY_SCHEMA_VERSION
        },
        "engine_version": engine_version,
        "output_paths": outputs,
        "integrations": {
            "webhook": {
                "enabled": bool(cli_flags.get("webhook_enabled", False)),
                "url_present": bool(cli_flags.get("webhook_url")),
                "timeout": float(cli_flags.get("webhook_timeout", 2.0)),
            }
        },
        "evo": {
            "enabled": bool(cli_flags.get("evo_enabled", False)),
            "trial_tag": cli_flags.get("trial_tag"),
        },
        "ui": {"report_url": None, "journal_url": None},
    }
