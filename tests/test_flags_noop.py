from __future__ import annotations
import copy

from crapssim_control.flags import read_flags, ensure_meta_flags, set_flag
from crapssim_control.guardrails import apply_guardrails
from crapssim_control.hot_table import scale_bets_if_hot


def _spec():
    return {
        "meta": {"version": 0, "name": "X"},
        "table": {"bubble": False, "level": 10},
        "variables": {"mode": "Main"},
        "modes": {"Main": {"template": {}}},
        "rules": [],
    }


def test_flags_default_off():
    spec = _spec()
    hot, grd = read_flags(spec)
    assert hot is False and grd is False


def test_flags_setters():
    spec = _spec()
    ensure_meta_flags(spec)
    set_flag(spec, "hot_table", True)
    set_flag(spec, "guardrails", False)
    hot, grd = read_flags(spec)
    assert hot is True and grd is False


def test_noop_processors_return_intents_unchanged():
    spec = _spec()
    vs = object()
    intents = [{"bet": "pass", "amount": 10.0}, {"bet": "field", "amount": 5.0}]
    i1 = apply_guardrails(copy.deepcopy(spec), vs, copy.deepcopy(intents))
    i2 = scale_bets_if_hot(copy.deepcopy(spec), vs, copy.deepcopy(intents))
    assert i1 == intents
    assert i2 == intents
