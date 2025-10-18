import csv
import json
from pathlib import Path

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED, ROLL, SEVEN_OUT
from crapssim_control.schemas import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION
from tests import skip_csv_preamble

_BASELINE_JOURNAL = Path(__file__).resolve().parent.parent / "baselines" / "phase2" / "journal.csv"
_BASELINE_HEADER = _BASELINE_JOURNAL.read_text(encoding="utf-8").splitlines()[0]
_BASELINE_COLUMNS = _BASELINE_HEADER.split(",")


def _spec(csv_path: Path, *, embed_analytics: bool = True, report_path: Path | None = None):
    run_cfg = {
        "csv": {
            "enabled": True,
            "path": str(csv_path),
            "append": False,
            "run_id": "SCHEMA-T",
            "seed": 313,
            "embed_analytics": embed_analytics,
        },
    }
    if report_path is not None:
        run_cfg["report"] = {
            "enabled": True,
            "path": str(report_path),
            "auto": False,
        }
    else:
        run_cfg["report"] = {"enabled": False, "auto": False}

    return {
        "table": {},
        "variables": {"units": 10},
        "modes": {"Main": {"template": {"pass_line": 10, "place_6": 12}}},
        "run": run_cfg,
        "rules": [],
    }


def _drive_run(ctrl: ControlStrategy) -> None:
    ctrl.handle_event(
        {
            "type": COMEOUT,
            "roll": 7,
            "bankroll_before": 1000,
            "bankroll_after": 1000,
        },
        current_bets={},
    )
    ctrl.handle_event(
        {
            "type": POINT_ESTABLISHED,
            "point": 6,
            "roll": 6,
            "bankroll_before": 1000,
            "bankroll_after": 1010,
        },
        current_bets={},
    )
    ctrl.handle_event(
        {
            "type": ROLL,
            "point": 6,
            "roll": 8,
            "bankroll_before": 1010,
            "bankroll_after": 1000,
        },
        current_bets={},
    )
    ctrl.handle_event(
        {
            "type": SEVEN_OUT,
            "point": 6,
            "roll": 7,
            "bankroll_before": 1000,
            "bankroll_after": 980,
        },
        current_bets={},
    )
    ctrl.finalize_run()


def _read_csv_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as fh:
        skip_csv_preamble(fh)
        reader = csv.DictReader(fh)
        return reader.fieldnames or [], list(reader)


def test_report_contains_versions(tmp_path: Path):
    csv_path = tmp_path / "journal.csv"
    report_path = tmp_path / "report.json"

    ctrl = ControlStrategy(_spec(csv_path, report_path=report_path))
    _drive_run(ctrl)

    report = ctrl.generate_report()
    assert report.get("journal_schema_version") == JOURNAL_SCHEMA_VERSION
    assert report.get("summary_schema_version") == SUMMARY_SCHEMA_VERSION

    assert report_path.exists()
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved.get("journal_schema_version") == JOURNAL_SCHEMA_VERSION
    assert saved.get("summary_schema_version") == SUMMARY_SCHEMA_VERSION


def test_csv_header_has_version(tmp_path: Path):
    csv_path = tmp_path / "journal.csv"

    ctrl = ControlStrategy(_spec(csv_path, embed_analytics=False))
    _drive_run(ctrl)

    assert csv_path.exists()
    with csv_path.open(encoding="utf-8") as fh:
        non_empty = [line.strip() for line in fh if line.strip()]
    assert non_empty[0] == f"# journal_schema_version: {JOURNAL_SCHEMA_VERSION}"
    assert non_empty[1] == _BASELINE_HEADER


def test_flag_off_no_schema_drift(tmp_path: Path):
    csv_path = tmp_path / "journal.csv"

    ctrl = ControlStrategy(_spec(csv_path, embed_analytics=False))
    _drive_run(ctrl)

    header_line = ""
    with csv_path.open(encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            header_line = stripped
            break
    assert header_line == _BASELINE_HEADER

    fieldnames, rows = _read_csv_rows(csv_path)
    assert fieldnames == _BASELINE_COLUMNS
    assert rows, "expected at least one row"
    first_row_keys = list(rows[0].keys())
    assert first_row_keys == _BASELINE_COLUMNS


def test_flag_on_columns_additive(tmp_path: Path):
    csv_path = tmp_path / "journal.csv"

    ctrl = ControlStrategy(_spec(csv_path, embed_analytics=True))
    _drive_run(ctrl)

    fieldnames, rows = _read_csv_rows(csv_path)
    assert rows, "expected at least one row"
    expected_additive = ["hand_id", "roll_in_hand", "bankroll_after", "drawdown_after"]
    assert fieldnames[: len(_BASELINE_COLUMNS)] == _BASELINE_COLUMNS
    assert fieldnames[len(_BASELINE_COLUMNS):] == expected_additive

    sample_row = rows[0]
    for key in expected_additive:
        assert key in sample_row
