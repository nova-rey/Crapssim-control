from crapssim_control.commands.run_cmd import _finalize_per_run_artifacts
from crapssim_control.schemas import JOURNAL_SCHEMA_VERSION


def test_finalize_per_run_artifacts_creates_journal_stub(tmp_path):
    run_dir = tmp_path / "run"
    summary = {"run": "id"}
    manifest = {"run": {"flags": {}}}

    _finalize_per_run_artifacts(
        run_dir=run_dir,
        manifest=manifest,
        summary=summary,
        export_summary_path=None,
        journal_src=None,
    )

    journal_path = run_dir / "journal.csv"
    assert journal_path.exists()
    text = journal_path.read_text(encoding="utf-8")
    assert f"# journal_schema_version: {JOURNAL_SCHEMA_VERSION}" in text


def test_finalize_per_run_artifacts_keeps_existing_journal(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    journal_path = run_dir / "journal.csv"
    journal_path.write_text("existing data", encoding="utf-8")

    _finalize_per_run_artifacts(
        run_dir=run_dir,
        manifest={},
        summary={},
        export_summary_path=None,
        journal_src=None,
    )

    assert journal_path.read_text(encoding="utf-8") == "existing data"
