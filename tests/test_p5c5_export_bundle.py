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
                # No explicit template needed; controller fallback will synthesize an action on 6
                "template": {}
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
                # keep report_path here for legacy lookups too
                "report_path": str(report_path),
            },
            "report": {
                "path": str(report_path),
                # nested export block (one possible lookup path)
                "export": {
                    "path": str(export_root),
                    "compress": compress,
                },
            },
            # top-level export block (alternate lookup path)
            "export": {
                "path": str(export_root),
                "compress": compress,
            },
        },
        "rules": [],
    }


def _drive_minimal_run(ctrl: ControlStrategy):
    # comeout: no actions; point 6 should generate at least one action via template/fallback
    assert ctrl.handle_event({"type": COMEOUT}, current_bets={}) == []
    acts = ctrl.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    assert len(acts) >= 1
    ctrl.finalize_run()


#@pytest.mark.xfail(reason="P5C5 export bundling not implemented yet", strict=False)
def test_export_folder_bundle(tmp_path: Path):
    csv_path = tmp_path / "journal.csv"
    meta_path = tmp_path / "meta.json"
    report_path = tmp_path / "report.json"
    export_root = tmp_path / "export_folder"

    spec = _spec(csv_path, meta_path, report_path, export_root, compress=False)
    c = ControlStrategy(spec)

    _drive_minimal_run(c)

    # Expect an export directory created under export_root (named by run_id + timestamp or similar)
    assert export_root.exists(), "Export root should be created"
    # Find the most recent subfolder
    subdirs = [p for p in export_root.iterdir() if p.is_dir()]
    assert subdirs, "An export subfolder should be created inside export_root"
    export_dir = max(subdirs, key=lambda p: p.stat().st_mtime)

    manifest = export_dir / "manifest.json"
    assert manifest.exists(), "manifest.json should be present in the export folder"

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "identity" in data
    assert "artifacts" in data
    arts = data["artifacts"]
    # Paths in manifest should point at the copies inside the export folder
    assert (export_dir / Path(arts.get("csv", ""))).exists(), "CSV artifact should exist in export"
    # meta may be optional in some modes, but in this test we expect it
    assert (export_dir / Path(arts.get("meta", ""))).exists(), "Meta artifact should exist in export"
    assert (export_dir / Path(arts.get("report", ""))).exists(), "Report artifact should exist in export"


@pytest.mark.xfail(reason="P5C5 export bundling (zip mode) not implemented yet", strict=False)
def test_export_zip_bundle(tmp_path: Path):
    csv_path = tmp_path / "journal.csv"
    meta_path = tmp_path / "meta.json"
    report_path = tmp_path / "report.json"
    export_root = tmp_path / "export_zip"

    spec = _spec(csv_path, meta_path, report_path, export_root, compress=True)
    c = ControlStrategy(spec)

    _drive_minimal_run(c)

    # Expect a zip file created in export_root
    assert export_root.exists(), "Export root should be created"
    zips = sorted(export_root.glob("*.zip"))
    assert zips, "A .zip export should be created when compress=True"
    zip_path = zips[-1]

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = set(zf.namelist())
        # manifest.json presence
        assert any(n.endswith("manifest.json") for n in names), "manifest.json should be in the zip"

        # Read and validate manifest
        manifest_name = next(n for n in names if n.endswith("manifest.json"))
        with zf.open(manifest_name) as fp:
            data = json.loads(fp.read().decode("utf-8"))

        arts = data.get("artifacts", {})
        # The artifacts should also be present in the zip by the relative paths listed
        for key in ("csv", "meta", "report"):
            rel = arts.get(key)
            assert rel, f"Artifact key '{key}' should be listed in manifest"
            assert any(n.endswith(rel) for n in names), f"{key} artifact '{rel}' should be in the zip"