import json
from pathlib import Path

from crapssim_control.controller import ControlStrategy
from crapssim_control.events import COMEOUT, POINT_ESTABLISHED, ROLL


def _base_spec(tape_path: Path, mode: str) -> dict:
    return {
        "table": {"bubble": False, "level": 10},
        "modes": {"base": {"template": {}}},
        "variables": {"units": 10},
        "run": {
            "webhooks": {"enabled": False},
            "http_commands": {"enabled": False},
            "external": {"mode": mode, "tape_path": str(tape_path)},
        },
    }


def _drive_session(ctrl: ControlStrategy) -> None:
    ctrl.handle_event({"type": COMEOUT}, current_bets={})
    ctrl.handle_event({"type": POINT_ESTABLISHED, "point": 6}, current_bets={})
    ctrl.handle_event({"type": ROLL, "roll": 8, "point": 6, "on_comeout": False}, current_bets={})


def test_command_tape_replay_matches_live(tmp_path):
    tape_path = tmp_path / "command_tape_live.jsonl"
    live_spec = _base_spec(tape_path, "live")
    live_ctrl = ControlStrategy(live_spec)
    live_ctrl.journal.path = str(tmp_path / "live_decision_journal.jsonl")

    commands = [
        (
            "regress",
            {"target": {"selector": ["6", "8"]}},
            "cid-1",
        ),
        (
            "press",
            {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}},
            "cid-2",
        ),
    ]

    for action, args, corr in commands:
        ok, reason = live_ctrl.command_queue.enqueue(
            {
                "run_id": live_ctrl.run_id,
                "action": action,
                "args": args,
                "source": "test",
                "correlation_id": corr,
            }
        )
        assert ok, reason

    _drive_session(live_ctrl)

    live_entries = [
        json.loads(line)
        for line in Path(live_ctrl.journal.path).read_text(encoding="utf-8").splitlines()
        if line and "external" in line
    ]
    assert live_entries, "live run did not record external decisions"

    replay_spec = _base_spec(tape_path, "replay")
    replay_ctrl = ControlStrategy(replay_spec)
    replay_ctrl.journal.path = str(tmp_path / "replay_decision_journal.jsonl")

    _drive_session(replay_ctrl)

    replay_entries = [
        json.loads(line)
        for line in Path(replay_ctrl.journal.path).read_text(encoding="utf-8").splitlines()
        if line and "external" in line
    ]

    assert len(replay_entries) == len(live_entries)
    live_summary = [
        {
            "action": entry["action"],
            "args": entry.get("args", {}),
            "executed": entry.get("executed"),
            "rejection_reason": entry.get("rejection_reason"),
        }
        for entry in live_entries
    ]
    replay_summary = [
        {
            "action": entry["action"],
            "args": entry.get("args", {}),
            "executed": entry.get("executed"),
            "rejection_reason": entry.get("rejection_reason"),
        }
        for entry in replay_entries
    ]

    assert replay_summary == live_summary
    assert replay_ctrl.run_id == live_ctrl.run_id
    assert not replay_ctrl._http_commands_enabled
