from crapssim_control.manifest import generate_manifest
from crapssim_control.schemas import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION


def test_manifest_structure(tmp_path):
    outputs = {
        "journal": str(tmp_path / "journal.csv"),
        "report": str(tmp_path / "report.json"),
        "manifest": str(tmp_path / "manifest.json"),
    }
    manifest = generate_manifest("spec.json", {"strict": False}, outputs)
    assert "run_id" in manifest
    assert "timestamp" in manifest
    assert manifest["schema"]["journal"] == JOURNAL_SCHEMA_VERSION
    assert manifest["schema"]["summary"] == SUMMARY_SCHEMA_VERSION
    assert set(outputs.keys()).issubset(set(manifest["output_paths"].keys()))
