from crapssim_control.behavior import BehaviorEngine, DecisionsJournal
from crapssim_control.behavior.dsl_parser import RuleDef


def test_conflict_first_applies(tmp_path):
    r1 = RuleDef(id="a", when="profit >= 0", then="press", scope=None, cooldown=None, guards=[])
    r1.args = {"bet":"place_6","units":1}
    r2 = RuleDef(id="b", when="profit >= 0", then="regress", scope=None, cooldown=None, guards=[])
    r2.args = {"bet":"place_6","units":1}
    be = BehaviorEngine([r1, r2], once_per_window=True)
    dj = DecisionsJournal(tmp_path)
    snap = {"roll_index":1,"profit":0}
    intent = be.evaluate_window("after_resolve", snap, dj)
    assert intent["verb"] == "press"
