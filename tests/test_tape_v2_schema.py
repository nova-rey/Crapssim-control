import pytest

from crapssim_control.external.command_tape import record_command_tape, iter_commands


def test_record_and_iter_tape_v2_roundtrip():
    tape = record_command_tape(
        [
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
    )
    verbs = []
    for verb, _ in iter_commands(tape):
        verbs.append(verb)
    assert verbs == ["press", "apply_policy"]


def test_schema_mismatch_raises():
    bad = {"tape_schema": "0.9", "commands": []}
    with pytest.raises(ValueError):
        list(iter_commands(bad))
