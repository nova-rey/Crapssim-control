import json


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_manifest_and_report_contract():
    manifest = _load("baselines/phase5/manifest.json")
    report = _load("baselines/phase5/report.json")

    assert manifest["run_id"] == report["run_id"]

    assert manifest["schema"]["journal"] == "1.2"
    assert manifest["schema"]["summary"] == "1.2"
    assert report["journal_schema_version"] == "1.2"
    assert report["summary_schema_version"] == "1.2"

    assert report["manifest_path"].endswith("manifest.json")

    meta = report["metadata"]
    assert {"name", "version", "python"}.issubset(meta["engine"].keys())
    arts = meta["artifacts"]
    assert {"journal", "report", "manifest"}.issubset(arts.keys())

    rf = meta.get("run_flags", {})
    assert "webhook_url_masked" in rf
    assert any(key.endswith("_source") for key in rf.keys())
