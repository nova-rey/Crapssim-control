import zipfile
import json
from pathlib import Path

from crapssim_control.bundles import import_evo_bundle, SchemaMismatchError, BundleReadError


def _make_zip(tmp: Path, files: dict[str, dict | str]) -> Path:
    zpath = tmp / "evo_bundle.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            if isinstance(content, dict):
                z.writestr(name, json.dumps(content))
            else:
                z.writestr(name, content)
    return zpath


def test_import_evo_bundle_happy_path(tmp_path: Path):
    files = {
        "spec.json": {"name": "X", "lineage_id": "abc", "odds_working_on_comeout": True},
        "manifest.json": {"journal_schema_version": "1.1", "summary_schema_version": "1.1"},
        "report.json": {"summary_schema_version": "1.1"},
        "journal.csv": "roll,bankroll\n1,1000\n",
    }
    zpath = _make_zip(tmp_path, files)
    spec, meta = import_evo_bundle(zpath)
    assert isinstance(spec, dict)
    assert "lineage_id" not in spec  # stripped
    assert "working_on_comeout" in spec  # normalized key
    assert meta["source"] == "evo_zip"
    assert "manifest.json" in meta["present"]


def test_import_evo_bundle_schema_mismatch(tmp_path: Path):
    files = {
        "spec.json": {"name": "Y"},
        "manifest.json": {"journal_schema_version": "9.9", "summary_schema_version": "9.9"},
    }
    zpath = _make_zip(tmp_path, files)
    try:
        import_evo_bundle(zpath)
        assert False, "expected SchemaMismatchError"
    except SchemaMismatchError:
        pass


def test_import_evo_bundle_missing_spec_raises(tmp_path: Path):
    files = {
        "manifest.json": {"journal_schema_version": "1.1", "summary_schema_version": "1.1"},
    }
    zpath = _make_zip(tmp_path, files)
    try:
        import_evo_bundle(zpath)
        assert False, "expected BundleReadError"
    except BundleReadError:
        pass
