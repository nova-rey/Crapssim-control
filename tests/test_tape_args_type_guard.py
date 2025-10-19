import pytest

from crapssim_control.external.command_tape import iter_commands, record_command_tape


def test_record_rejects_non_dict_args():
    with pytest.raises(ValueError):
        record_command_tape([{"verb": "press", "args": [1, 2, 3]}])


def test_iter_rejects_non_dict_args():
    tape = {"tape_schema": "1.0", "commands": [{"verb": "press", "args": [1, 2]}]}
    with pytest.raises(ValueError):
        list(iter_commands(tape))
