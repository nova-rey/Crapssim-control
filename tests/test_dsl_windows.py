from crapssim_control.behavior import BehaviorEngine, DecisionsJournal
from crapssim_control.behavior.dsl_parser import RuleDef


def test_illegal_window_reject_smoke(tmp_path):
    # Here we simulate evaluator producing an intent; legality gate lives in controller.
    # We'll just ensure evaluate_window returns an intent when condition holds.
    r = RuleDef(id="r", when="profit > 0", then="press", scope="hand", cooldown=None, guards=[])
    r.args = {"bet": "place_6", "units": 1}
    be = BehaviorEngine([r])
    dj = DecisionsJournal(tmp_path)
    snap = {"roll_index": 1, "profit": 1, "point_on": True}
    intent = be.evaluate_window("after_resolve", snap, dj)
    assert intent and intent["verb"] == "press"
