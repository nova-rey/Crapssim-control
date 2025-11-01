from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from shutil import copyfile
from typing import Any, Optional

from crapssim_control.schemas import JOURNAL_SCHEMA_VERSION
from crapssim_control.utils.io_atomic import write_json_atomic


def _ensure_journal_stub(journal_path: Path) -> None:
    """Write a minimal journal.csv stub when no source data is available."""

    try:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:  # pragma: no cover - defensive
        return

    try:
        journal_path.write_text(
            f"# journal_schema_version: {JOURNAL_SCHEMA_VERSION}\n",
            encoding="utf-8",
        )
    except Exception:  # pragma: no cover - defensive
        pass


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


def _finalize_per_run_artifacts(
    *,
    run_dir: Path,
    manifest: Optional[dict[str, Any]],
    summary: Optional[dict[str, Any]],
    export_summary_path: Optional[Path],
    journal_src: Optional[Path],
) -> None:
    """Always materialize manifest.json and summary.json beside decisions.csv."""

    run_dir.mkdir(parents=True, exist_ok=True)

    summary_path = run_dir / "summary.json"
    manifest_path = run_dir / "manifest.json"

    normalized_summary: Optional[dict[str, Any]] = None
    if isinstance(summary, Mapping) and summary:
        normalized_summary = dict(summary)

    if normalized_summary is not None:
        write_json_atomic(summary_path, normalized_summary)
    elif export_summary_path is not None and Path(export_summary_path).exists():
        copyfile(Path(export_summary_path), summary_path)
    else:
        write_json_atomic(
            summary_path,
            _fallback_summary("no summary returned by controller"),
        )

    manifest_payload: dict[str, Any]
    if isinstance(manifest, Mapping) and manifest:
        manifest_payload = dict(manifest)
    else:
        manifest_payload = {"run": {"flags": {}}, "identity": {"source": "fallback"}}

    write_json_atomic(manifest_path, manifest_payload)

    dest = run_dir / "journal.csv"

    if journal_src:
        journal_path = Path(journal_src)
        if journal_path.exists():
            try:
                if dest.resolve() == journal_path.resolve():
                    return
            except FileNotFoundError:
                pass
            copyfile(journal_path, dest)
            return

    needs_stub = False
    try:
        needs_stub = not dest.exists() or dest.stat().st_size == 0
    except OSError:
        needs_stub = True

    if needs_stub:
        _ensure_journal_stub(dest)


__all__ = ["_finalize_per_run_artifacts", "_fallback_summary"]
