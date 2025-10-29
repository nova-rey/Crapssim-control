import hashlib
import json

from crapssim_control.engine_adapter import VanillaAdapter
from crapssim_control.external.command_tape import record_command_tape
from crapssim_control.replay import ReplayRunner
from crapssim_control.report import build_report


def _digest(o) -> str:
    return hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()


def test_live_replay_digest_match():
    cmds = [
        {
            "verb": "press",
            "args": {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}},
        },
        {
            "verb": "apply_policy",
            "args": {
                "policy": {
                    "name": "martingale_v1",
                    "args": {"step_key": "6", "delta": 6, "max_level": 2},
                }
            },
        },
    ]
    tape = record_command_tape(cmds)
    seed = 13579

    live = VanillaAdapter()
    live.set_seed(seed)
    for c in cmds:
        live.apply_action(c["verb"], c["args"])
    live_snap = live.snapshot_state()

    rep = VanillaAdapter()
    snap_replay = ReplayRunner(
        controller=type("C", (), {"adapter": rep})(), tape=tape, seed=seed
    ).run()

    report = build_report(live_snap, snap_replay, meta={"seed": seed})
    assert report["replay_verified"] is True
    assert _digest(live_snap) == _digest(snap_replay)
