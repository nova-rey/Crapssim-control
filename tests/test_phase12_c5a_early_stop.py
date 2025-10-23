import pytest


def mk_adapter(spec=None):
    from crapssim_control.engine_adapter import VanillaAdapter
    a = VanillaAdapter()
    a.start_session(spec or {"run": {"journal": {"explain": False}}})
    # make transport.step a no-op
    a.transport.step = lambda dice=None, seed=None: {"rolled": True}
    return a


def test_bankroll_zero_triggers_stop(monkeypatch):
    a = mk_adapter()
    monkeypatch.setattr(a, "snapshot_state", lambda: {"bankroll": 0.0, "roll_in_hand": 5})
    out = a.step_roll((3, 4))
    assert out.get("status") == "terminated"
    assert out.get("reason") == "bankroll_exhausted"


def test_unactionable_due_to_table_min(monkeypatch):
    a = mk_adapter({"run": {"journal": {"explain": False},
                              "table_mins": {"line": 5, "field": 5,
                                              "place_unit": {"default": 5, "6": 6, "8": 6},
                                              "odds_unit": 5}}})
    # Bankroll stranded at $4 with comeout (no point)
    monkeypatch.setattr(a, "snapshot_state", lambda: {"bankroll": 4.0, "point_on": False,
                                                        "roll_in_hand": 1, "active_bets_sum": 0})
    out = a.step_roll((1, 1))
    assert out.get("status") == "terminated"
    assert out.get("reason") == "unactionable_bankroll"


def test_policy_caps_make_unactionable(monkeypatch):
    # Caps below table min → unactionable
    a = mk_adapter({"run": {
        "journal": {"explain": False},
        "policy": {"enforce": True},
        "risk": {"bet_caps": {"place_6": 4}},  # below $6 unit
        "table_mins": {"place_unit": {"default": 5, "6": 6, "8": 6}}
    }})
    # Enough bankroll but caps forbid meeting mins
    monkeypatch.setattr(a, "snapshot_state", lambda: {"bankroll": 50.0, "point_on": True, "active_bets_sum": 0})
    out = a.step_roll((2, 3))
    assert out.get("status") == "terminated"
    assert out.get("reason") == "unactionable_bankroll"


def test_flags_disable_early_stop(monkeypatch):
    a = mk_adapter({"run": {"stop_on_bankrupt": False, "stop_on_unactionable": False}})
    calls = {"rolled": 0}
    a.transport.step = lambda dice=None, seed=None: calls.__setitem__("rolled", calls["rolled"] + 1) or {"rolled": True}
    monkeypatch.setattr(a, "snapshot_state", lambda: {"bankroll": 0.0, "roll_in_hand": 2})
    out = a.step_roll((3, 4))
    assert out.get("status") != "terminated"
    assert calls["rolled"] == 1
