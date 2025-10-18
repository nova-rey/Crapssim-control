"""
Run Manifest generator: captures run metadata, CLI flags, schema versions, and outputs.
"""
from uuid import uuid4
from datetime import datetime
from .schemas import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION


def iso_now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def generate_manifest(spec_file: str, cli_flags: dict, outputs: dict, engine_version: str = None):
    return {
        "run_id": str(uuid4()),
        "timestamp": iso_now(),
        "spec_file": spec_file,
        "cli_flags": cli_flags,
        "schema": {
            "journal": JOURNAL_SCHEMA_VERSION,
            "summary": SUMMARY_SCHEMA_VERSION
        },
        "engine_version": engine_version,
        "output_paths": outputs
    }
