from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Optional, Iterable

from .errors import ExportEmptyError

_REQUIRED = ("manifest.json", "journal.csv")
_OPTIONAL = ("report.json", "decisions.csv")


def _ensure_path(p) -> Path:
    return p if isinstance(p, Path) else Path(p)


def _validate_run_dir(run_dir: Path) -> None:
    missing = [name for name in _REQUIRED if not (run_dir / name).exists()]
    if missing:
        raise ExportEmptyError(f"export_bundle: missing required artifacts: {missing}")


def _iter_files(run_dir: Path) -> Iterable[Path]:
    for name in _REQUIRED + _OPTIONAL:
        p = run_dir / name
        if p.exists() and p.is_file():
            yield p


def export_bundle(run_dir, output_path: Optional[str | os.PathLike] = None) -> Path:
    """
    Create a zip archive containing CSC run artifacts suitable for Evo ingestion.
    Includes: manifest.json, journal.csv, and optionally report.json, decisions.csv.
    Returns the path to the created .zip.
    """
    run_dir = _ensure_path(run_dir)
    if output_path is None:
        output_path = run_dir / "csc_bundle.zip"
    out = _ensure_path(output_path)

    _validate_run_dir(run_dir)
    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in _iter_files(run_dir):
            z.write(p, arcname=p.name)
    return out
