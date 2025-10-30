from crapssim_control.behavior import BehaviorEngine, DecisionsJournal
from crapssim_control.behavior.dsl_parser import RuleDef


def test_cooldown_rolls(tmp_path):
    r = RuleDef(id="r", when="profit >= 0", then="press", scope="roll", cooldown={"rolls":2}, guards=[])
    r.args = {"bet":"place_6","units":1}
    be = BehaviorEngine([r])
    dj = DecisionsJournal(tmp_path)
    snap = {"roll_index":1,"profit":0}
    assert be.evaluate_window("after_resolve", snap, dj) is not None
    be.on_scope_advance("roll")
    assert be.evaluate_window("after_resolve", snap, dj) is None
    be.on_scope_advance("roll")
    assert be.evaluate_window("after_resolve", snap, dj) is None
    be.on_scope_advance("roll")
    assert be.evaluate_window("after_resolve", snap, dj) is not None
