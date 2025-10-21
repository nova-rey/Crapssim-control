import pytest

from crapssim_control.engine_adapter import CrapsSimAdapter
from crapssim_control.replay_tester import run_replay_parity

crapssim = pytest.importorskip("crapssim")


@pytest.fixture()
def live_engine_adapter():
    adapter = CrapsSimAdapter()
    adapter.start_session({})
    return adapter


def test_error_codes_consistent(live_engine_adapter):
    adapter = live_engine_adapter
    result = adapter.apply_action("hardway_bet", {"number": 13, "amount": 10})
    assert result["rejected"]
    assert result["code"] in ("illegal_number", "engine_error")


def test_rejected_effect_logging(tmp_path):
    from crapssim_control.journal import append_effect_summary_line

    path = tmp_path / "journal.jsonl"
    append_effect_summary_line({"rejected": True, "code": "illegal_number", "reason": "bad"}, path=path)
    data = path.read_text()
    assert "rejected_effect" in data


def test_replay_parity_succeeds():
    assert run_replay_parity(seed=7, rolls=100)


def test_perf_sanity():
    from crapssim_control.replay_tester import run_perf_test

    res = run_perf_test(rolls=1000)
    assert res["rps"] > 200
