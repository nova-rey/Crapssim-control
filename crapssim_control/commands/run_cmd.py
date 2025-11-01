from __future__ import annotations

from __future__ import annotations

from pathlib import Path
from shutil import copyfile
from typing import Any, Optional

from crapssim_control.utils.io_atomic import write_json_atomic


def _fallback_summary(err_msg: str) -> dict[str, Any]:
    return {
        "summary_status": "fallback",
        "incomplete": True,
        "errors": [
            {"phase": "summary", "type": "MissingSummary", "message": err_msg},
        ],
        "stats": {},
        "bankroll": {},
        "schema_version": "1.1",
        "summary_schema_version": "1.1",
    }


def _emit_per_run_artifacts(
    run_dir: Path,
    manifest: dict[str, Any],
    summary: Optional[dict[str, Any]] = None,
    export_summary_path: Optional[Path] = None,
    journal_src: Optional[Path] = None,
) -> None:
    """Ensure summary.json + manifest.json live in run_dir. Copy journal if available."""

    run_dir.mkdir(parents=True, exist_ok=True)

    summary_path = run_dir / "summary.json"
    manifest_path = run_dir / "manifest.json"

    if summary and isinstance(summary, dict):
        write_json_atomic(summary_path, summary)
    elif export_summary_path and export_summary_path.exists():
        copyfile(export_summary_path, summary_path)
    else:
        write_json_atomic(
            summary_path,
            _fallback_summary("controller returned no summary"),
        )

    write_json_atomic(manifest_path, manifest)

    if journal_src and journal_src.exists():
        dest = run_dir / "journal.csv"
        try:
            if dest.resolve() == journal_src.resolve():
                return
        except FileNotFoundError:
            # One of the paths might not exist yet; fall back to copy
            pass
        copyfile(journal_src, dest)


__all__ = ["_emit_per_run_artifacts", "_fallback_summary"]
