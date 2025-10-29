from crapssim_control.engine_adapter import VanillaAdapter
from crapssim_control.external.command_tape import record_command_tape
from crapssim_control.replay import ReplayRunner


def test_live_vs_replay_parity_simple_tape():
    seed = 777
    commands = [
        {
            "verb": "press",
            "args": {"target": {"bet": "6"}, "amount": {"mode": "dollars", "value": 6}},
        },
        {
            "verb": "apply_policy",
            "args": {
                "policy": {
                    "name": "martingale_v1",
                    "args": {"step_key": "6", "delta": 6, "max_level": 3},
                }
            },
        },
        {"verb": "regress", "args": {"target": {"selector": ["6", "8"]}}},
        {"verb": "same_bet", "args": {"target": {"bet": "pass"}}},
        {"verb": "switch_profile", "args": {"details": {"profile": "baseline"}}},
    ]
    tape = record_command_tape(commands)

    live = VanillaAdapter()
    live.set_seed(seed)
    for cmd in commands:
        live.apply_action(cmd["verb"], cmd["args"])
    snapshot_live = live.snapshot_state()

    replay_adapter = VanillaAdapter()
    controller = type("Controller", (), {"adapter": replay_adapter})()
    replay = ReplayRunner(controller=controller, tape=tape, seed=seed)
    snapshot_replay = replay.run()

    assert snapshot_live == snapshot_replay
