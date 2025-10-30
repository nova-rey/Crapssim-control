from crapssim_control.behavior import BehaviorEngine, DecisionsJournal
from crapssim_control.behavior.dsl_parser import RuleDef


def test_determinism_same_input_same_output(tmp_path):
    r = RuleDef(id="r", when="point_on == true", then="switch_profile", scope=None, cooldown=None, guards=[])
    r.args = {"name":"safe_mode"}
    snap = {"roll_index":10,"point_on":True}
    for _ in range(3):
        be = BehaviorEngine([r])
        dj = DecisionsJournal(tmp_path)
        intent = be.evaluate_window("after_point_set", snap, dj)
        assert intent == {"verb":"switch_profile","name":"safe_mode"}
