from crapssim_control.engine_adapter import VanillaAdapter
from crapssim_control.external.command_tape import record_command_tape
from crapssim_control.report import build_report
from crapssim_control.replay import ReplayRunner


def test_live_replay_parity_for_seeded_baseline():
    seed = 20251019
    cmds = [
        {"verb": "press", "args": {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}}},
        {"verb": "apply_policy", "args": {"policy": {"name": "martingale_v1", "args": {"step_key": "6", "delta": 6, "max_level": 3}}}},
        {"verb": "regress", "args": {"target": {"selector": ["6", "8"]}}},
        {"verb": "same_bet", "args": {"target": {"bet": "pass"}}},
    ]
    tape = record_command_tape(cmds)

    live = VanillaAdapter()
    live.set_seed(seed)
    for command in cmds:
        live.apply_action(command["verb"], command["args"])
    live_snapshot = live.snapshot_state()

    controller = type("Controller", (), {"adapter": VanillaAdapter()})()
    replay = ReplayRunner(controller=controller, tape=tape, seed=seed)
    replay_snapshot = replay.run()

    report = build_report(live_snapshot, replay_snapshot, meta={"seed": seed})
    assert report["replay_verified"] is True
