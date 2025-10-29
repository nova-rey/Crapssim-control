import json
from crapssim_control.schemas import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_manifest_and_report_contract():
    manifest = _load("baselines/phase5/manifest.json")
    report = _load("baselines/phase5/report.json")

    assert manifest["run_id"] == report["run_id"]

    assert manifest["schema"]["journal"] == JOURNAL_SCHEMA_VERSION
    assert manifest["schema"]["summary"] == SUMMARY_SCHEMA_VERSION
    assert report["journal_schema_version"] == JOURNAL_SCHEMA_VERSION
    assert report["summary_schema_version"] == SUMMARY_SCHEMA_VERSION

    assert report["manifest_path"].endswith("manifest.json")

    meta = report["metadata"]
    assert {"name", "version", "python"}.issubset(meta["engine"].keys())
    arts = meta["artifacts"]
    assert {"journal", "report", "manifest"}.issubset(arts.keys())

    rf = meta.get("run_flags", {})
    assert "webhook_url_masked" in rf
    assert any(key.endswith("_source") for key in rf.keys())
