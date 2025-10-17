# tests/test_controller_integration.py

from crapssim_control.controller import ControlStrategy


def _has_action(actions, action, bet_type):
    return any(a.get("action") == action and a.get("bet_type") == bet_type for a in actions)


def _get_amount(actions, bet_type):
    for a in actions:
        if a.get("action") == "set" and a.get("bet_type") == bet_type:
            return a.get("amount")
    return None


def _all_have_envelope(actions, *, source="template", source_id_prefix="template:"):
    return all(("source" in a and "id" in a and a["source"] == source and str(a["id"]).startswith(source_id_prefix))
               for a in actions)


def test_controller_renders_template_with_expressions_and_sets_bets():
    """
    End-to-end smoke test:
      - Controller consumes a template with string expressions (units*2, etc.)
      - Runtime template renderer evaluates via the safe evaluator
      - Controller returns action envelopes with numeric amounts
    """
    spec = {
        "variables": {"units": 5},
        "modes": {
            "Main": {
                "template": {
                    "pass": "units",
                    "place": {"6": "units * 2", "8": "units * 2"},
                }
            }
        },
        "rules": [],
    }

    ctrl = ControlStrategy(spec)

    # Simulate a point getting established
    ev_point = {"type": "point_established", "point": 6}
    plan = ctrl.handle_event(ev_point, current_bets={})

    # Envelope fields present and correct provenance
    assert _all_have_envelope(plan, source="template", source_id_prefix="template:Main")

    # Expect set actions for pass line and place 6/8
    assert _has_action(plan, "set", "pass_line")
    assert _has_action(plan, "set", "place_6")
    assert _has_action(plan, "set", "place_8")

    # Amounts should be numeric and > 0 (legalized)
    amt6 = _get_amount(plan, "place_6")
    amt8 = _get_amount(plan, "place_8")
    assert isinstance(amt6, (int, float)) and amt6 > 0
    assert isinstance(amt8, (int, float)) and amt8 > 0


def test_regression_after_third_roll_clears_place_6_and_8():
    """
    Controller should clear place_6/place_8 on the 3rd roll after the point is on.
    The emitted actions should carry envelope provenance and a regression note.
    """
    spec = {
        "variables": {"units": 5},
        "modes": {"Main": {"template": {"place": {"6": "units*2", "8": "units*2"}}}},
        "rules": [],
        "run": {"demo_fallbacks": True},
    }
    ctrl = ControlStrategy(spec)

    # Establish a point
    ctrl.handle_event({"type": "point_established", "point": 6}, current_bets={})

    # First two rolls: no regression clears expected
    a1 = ctrl.handle_event({"type": "roll"}, current_bets={})
    a2 = ctrl.handle_event({"type": "roll"}, current_bets={})
    assert not _has_action(a1, "clear", "place_6")
    assert not _has_action(a1, "clear", "place_8")
    assert not _has_action(a2, "clear", "place_6")
    assert not _has_action(a2, "clear", "place_8")

    # Third roll after point established should clear 6 and 8
    a3 = ctrl.handle_event({"type": "roll"}, current_bets={})
    assert _has_action(a3, "clear", "place_6")
    assert _has_action(a3, "clear", "place_8")

    # Envelope + note assertions
    assert _all_have_envelope(a3, source="template", source_id_prefix="template:regress_roll3")
    for a in a3:
        assert a.get("notes") == "auto-regress after 3rd roll"


def test_seven_out_resets_state_to_comeout():
    """
    After a seven_out, controller should reset to comeout state.
    """
    spec = {
        "variables": {"units": 5},
        "modes": {"Main": {"template": {"pass": "units"}}},
        "rules": [],
    }
    ctrl = ControlStrategy(spec)

    # Go to point-on state
    ctrl.handle_event({"type": "point_established", "point": 6}, current_bets={})
    snap = ctrl.state_snapshot()
    assert snap["point"] == 6
    assert snap["on_comeout"] is False

    # Seven out resets state
    ctrl.handle_event({"type": "seven_out"}, current_bets={})
    snap2 = ctrl.state_snapshot()
    assert snap2["point"] is None
    assert snap2["on_comeout"] is True