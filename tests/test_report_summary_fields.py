import json
from pathlib import Path


REQUIRED_KEYS = {
    "bankroll_final",
    "hands_played",
    "journal_lines",
    "external_executed",
    "external_rejected",
    "rejections_total",
}


def _is_int_like(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def test_final_report_summary_fields_present_and_typed():
    report_path = Path("baselines/phase6/final/report.json")
    data = json.loads(report_path.read_text(encoding="utf-8"))
    summary = data.get("summary") or {}

    for key in REQUIRED_KEYS:
        assert key in summary, f"missing summary field: {key}"

    assert isinstance(summary["bankroll_final"], (int, float))
    assert _is_int_like(summary["hands_played"]) or isinstance(summary["hands_played"], float)
    assert _is_int_like(summary["journal_lines"]) or isinstance(summary["journal_lines"], float)
    assert _is_int_like(summary["external_executed"]) or isinstance(
        summary["external_executed"], float
    )
    assert _is_int_like(summary["external_rejected"]) or isinstance(
        summary["external_rejected"], float
    )
    assert _is_int_like(summary["rejections_total"]) or isinstance(
        summary["rejections_total"], float
    )
