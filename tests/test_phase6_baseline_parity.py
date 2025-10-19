from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FINAL_DIR = REPO_ROOT / "baselines" / "phase6" / "final"
REPLAY_DIR = REPO_ROOT / "baselines" / "phase6" / "replay_validation"


def _load_report(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"report {path} did not decode to an object"
    return data


def _journal_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def test_phase6_baseline_parity() -> None:
    final_report = _load_report(FINAL_DIR / "report.json")
    replay_report = _load_report(REPLAY_DIR / "report.json")

    final_summary = final_report.get("summary", {}) or {}
    replay_summary = replay_report.get("summary", {}) or {}

    bankroll_keys = [
        "bankroll_low",
        "bankroll_peak",
        "max_drawdown",
        "total_rolls",
        "total_hands",
    ]
    for key in bankroll_keys:
        assert final_summary.get(key) == replay_summary.get(key), f"Mismatch for {key}"

    final_lines = _journal_lines(FINAL_DIR / "decision_journal.jsonl")
    replay_lines = _journal_lines(REPLAY_DIR / "decision_journal.jsonl")
    assert final_lines == replay_lines, "Replay journal length diverges from live baseline"
