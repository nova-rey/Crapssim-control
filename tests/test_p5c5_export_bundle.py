# tests/test_p5c5_export_bundle.py
import json
import zipfile
from pathlib import Path
import pytest

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED


def _spec(csv_path: Path, meta_path: Path, report_path: Path, export_root: Path, compress: bool):
    """
    Minimal spec used just for P5C5 export bundling tests.
    - CSV journaling enabled with known run_id/seed
    - meta.json path provided
    - report path provided
    - export configuration under both run.report.export and run.export (lenient)
      so either lookup strategy in controller will find it.
    """
    return {
        "modes": {
            "Main": {
                "template": {}  # no explicit template needed; fallback handles actions
            }
        },
        "variables": {"units": 10},
        "run": {
            "csv": {
                "enabled": True,
                "path": str(csv_path),
                "append": True,
                "run_id": "T-P5C5",
                "seed": 999,
            },
            "memory": {
                "meta_path": str(meta_path),
                "report_path": str(report_path),  # legacy lookup
            },
            "report": {
                "path": str(report_path),
                "export": {"path": str(export_root), "compress": compress},
            },
            "export": {"path": str(export_root), "compress": compress},
        },
        "rules": [],
    }


def _drive_minimal_run(ctrl: ControlStrategy):
    """Drive a minimal session: comeout → point 6 → finalize."""
    assert ctrl.handle_event({"type": COMEOUT}, current_bets={}) == []
    acts = ctrl.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert len(acts) >= 1, "Expected at least one action from POINT_ESTABLISHED(6)"
    ctrl.finalize_run()


def _resolve_artifact_path(base_dir: Path, rel_or_abs: str) -> Path:
    """Manifest may store artifact paths as relative (e.g. journal.csv) or absolute."""
    p = Path(rel_or_abs)
    return p if p.is_absolute() else (base_dir / p)


def test_export_folder_bundle(tmp_path: Path):
    """Verify non-compressed export bundle writes a manifest and expected artifacts."""
    csv_path = tmp_path / "journal.csv"
    meta_path = tmp_path / "meta.json"
    report_path = tmp_path / "report.json"
    export_root = tmp_path / "export_folder"

    spec = _spec(csv_path, meta_path, report_path, export_root, compress=False)
    c = ControlStrategy(spec)
    _drive_minimal_run(c)

    assert export_root.exists(), "Export root should be created"
    subdirs = [p for p in export_root.iterdir() if p.is_dir()]
    assert subdirs, "An export subfolder should be created inside export_root"
    export_dir = max(subdirs, key=lambda p: p.stat().st_mtime)

    manifest = export_dir / "manifest.json"
    assert manifest.exists(), "manifest.json should be present in the export folder"

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "identity" in data
    assert "artifacts" in data
    arts = data["artifacts"]

    csv_art = _resolve_artifact_path(export_dir, arts.get("csv", ""))
    meta_art = _resolve_artifact_path(export_dir, arts.get("meta", ""))
    report_art = _resolve_artifact_path(export_dir, arts.get("report", ""))

    assert csv_art.exists(), "CSV artifact should exist in export"
    assert meta_art.exists(), "Meta artifact should exist in export"
    assert report_art.exists(), "Report artifact should exist in export"


def test_export_zip_bundle(tmp_path: Path):
    """Verify compressed export bundle creates a valid zip with manifest and artifacts."""
    csv_path = tmp_path / "journal.csv"
    meta_path = tmp_path / "meta.json"
    report_path = tmp_path / "report.json"
    export_root = tmp_path / "export_zip"

    spec = _spec(csv_path, meta_path, report_path, export_root, compress=True)
    c = ControlStrategy(spec)
    _drive_minimal_run(c)

    assert export_root.exists(), "Export root should be created"
    zips = sorted(export_root.glob("*.zip"))
    assert zips, "A .zip export should be created when compress=True"
    zip_path = zips[-1]

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        assert any(n.endswith("manifest.json") for n in names), "manifest.json should be in the zip"

        manifest_name = next(n for n in names if n.endswith("manifest.json"))
        with zf.open(manifest_name) as fp:
            data = json.loads(fp.read().decode("utf-8"))

        arts = data.get("artifacts", {})
        for key in ("csv", "meta", "report"):
            rel = arts.get(key)
            assert rel, f"Artifact key '{key}' should be listed in manifest"
            assert any(n.endswith(rel) for n in names), f"{key} artifact '{rel}' should be in the zip"