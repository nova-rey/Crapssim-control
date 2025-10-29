import zipfile
import json
from pathlib import Path

from crapssim_control.bundles import export_bundle, ExportEmptyError


def _mk_run_dir(tmp: Path, with_decisions: bool = True) -> Path:
    run = tmp / "runA"
    run.mkdir(parents=True, exist_ok=True)
    (run / "manifest.json").write_text(
        json.dumps({"journal_schema_version": "1.1", "summary_schema_version": "1.1"}),
        encoding="utf-8",
    )
    (run / "journal.csv").write_text("roll,bankroll\n1,1000\n", encoding="utf-8")
    (run / "report.json").write_text(json.dumps({"hands": 1}), encoding="utf-8")
    if with_decisions:
        (run / "decisions.csv").write_text("ts,rule_id,action\n0.1,r1,press\n", encoding="utf-8")
    return run


def test_export_bundle_happy_path(tmp_path: Path):
    run = _mk_run_dir(tmp_path, with_decisions=True)
    zpath = export_bundle(run)
    assert zpath.exists()
    with zipfile.ZipFile(zpath, "r") as z:
        names = set(z.namelist())
        assert "manifest.json" in names
        assert "journal.csv" in names
        assert "report.json" in names
        assert "decisions.csv" in names


def test_export_bundle_missing_required_raises(tmp_path: Path):
    run = _mk_run_dir(tmp_path, with_decisions=False)
    (run / "journal.csv").unlink()  # remove required
    try:
        export_bundle(run)
        assert False, "expected ExportEmptyError"
    except ExportEmptyError:
        pass
