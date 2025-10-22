import pytest
from crapssim_control.engine_adapter import VanillaAdapter


@pytest.fixture
def adapter():
    return VanillaAdapter()


def test_cancel_bet_place(monkeypatch, adapter):
    called = {}

    def fake_take_down(num, amt=None):
        called["args"] = (num, amt)
        return {"ok": True}

    adapter.take_down = fake_take_down
    adapter.cancel_bet("place", 6, 12)
    assert called["args"] == (6, 12)


def test_cancel_bet_odds(monkeypatch, adapter):
    called = {}

    def fake_remove_odds(on=None, point=None):
        called["args"] = (on, point)
        return {"ok": True}

    adapter.remove_odds = fake_remove_odds
    adapter.cancel_bet("odds", ("come", 5))
    assert called["args"] == ("come", 5)


def test_cancel_bet_dc(monkeypatch, adapter):
    called = {}

    def fake_move_bet(from_=None, to=None):
        called["args"] = (from_, to)
        return {"ok": True}

    adapter.move_bet = fake_move_bet
    adapter.cancel_bet("dc", 8)
    assert called["args"] == (8, "off")


def test_cancel_bet_unknown(adapter):
    res = adapter.cancel_bet("foo", 6)
    assert "error" in res
