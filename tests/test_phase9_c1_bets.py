import pytest

from crapssim_control.engine_adapter import CrapsSimAdapter

crapssim = pytest.importorskip("crapssim")


@pytest.fixture()
def live_engine_adapter():
    adapter = CrapsSimAdapter()
    adapter.start_session({})
    return adapter


def test_field_and_hardways_integration(live_engine_adapter):
    adapter = live_engine_adapter
    adapter.apply_action("field_bet", {"amount": 10})
    adapter.apply_action("hardway_bet", {"number": 8, "amount": 12})
    snap = adapter.snapshot_state()
    assert "field" in snap["bets"]
    assert snap["bets"]["hardway_8"] >= 12


def test_come_dc_odds_flow(live_engine_adapter):
    adapter = live_engine_adapter
    res = adapter.apply_action("set_odds", {"side": "come", "number": 6, "amount": 30})
    assert res["result"] == "ok"
    snap = adapter.snapshot_state()
    assert "odds_come_6" in snap["bets"]


def test_illegal_odds_rejection(live_engine_adapter):
    adapter = live_engine_adapter
    res = adapter.apply_action("set_odds", {"side": "come", "number": 12, "amount": 10})
    assert res["rejected"]
    assert res["code"] == "illegal_window"
