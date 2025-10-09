# tests/test_actions_envelope.py

from typing import Any, Dict, List

from crapssim_control.actions import (
    SOURCE_TEMPLATE,
)
from crapssim_control.controller import ControlStrategy
from crapssim_control.templates_rt import diff_bets, render_template


def _all_have_envelope(actions: List[Dict[str, Any]], *, source="template", id_prefix="template:") -> bool:
    required = {"source", "id", "action", "bet_type", "amount", "notes"}
    for a in actions:
        if not required.issubset(a.keys()):
            return False
        if a["source"] != source:
            return False
        if not str(a["id"]).startswith(id_prefix):
            return False
    return True


def _has_exact(actions: List[Dict[str, Any]], d: Dict[str, Any]) -> bool:
    return any(a == d for a in actions)


def test_controller_template_diff_emits_envelopes_with_provenance_and_notes():
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

    # Simulate point establishment with empty current bets
    plan = ctrl.handle_event({"type": "point_established", "point": 6}, current_bets={})

    # All actions must be action envelopes with template provenance
    assert _all_have_envelope(plan, source=SOURCE_TEMPLATE, id_prefix="template:Main")

    # Controller stamps a consistent note for template diffs
    for a in plan:
        assert a.get("notes") == "template diff"


def test_controller_regression_actions_are_envelopes_with_notes():
    spec = {
        "variables": {"units": 5},
        "modes": {"Main": {"template": {"place": {"6": "units*2", "8": "units*2"}}}},
        "rules": [],
    }
    ctrl = ControlStrategy(spec)

    # Establish point, then roll thrice to trigger regression
    ctrl.handle_event({"type": "point_established", "point": 6}, current_bets={})
    ctrl.handle_event({"type": "roll"}, current_bets={})
    ctrl.handle_event({"type": "roll"}, current_bets={})
    actions = ctrl.handle_event({"type": "roll"}, current_bets={})

    # Two clear actions, correctly stamped
    assert _all_have_envelope(actions, source=SOURCE_TEMPLATE, id_prefix="template:regress_roll3")
    assert any(a.get("action") == "clear" and a.get("bet_type") == "place_6" for a in actions)
    assert any(a.get("action") == "clear" and a.get("bet_type") == "place_8" for a in actions)
    for a in actions:
        assert a.get("notes") == "auto-regress after 3rd roll"


def test_diff_bets_legacy_mode_returns_minimal_dicts():
    # Build a small desired state via render_template for realism
    state = {"units": 5, "bubble": False, "point": 0, "on_comeout": True}
    event = {"on_comeout": True}
    cfg = {"level": 10, "bubble": False}
    template = {
        "pass": "units*2",                   # 10
        "place": {"6": "units*2", "8": "units*2"},
        "field": "units",
    }
    desired = render_template(template, state, event, cfg)

    current = {"pass_line": {"amount": 10}, "place_6": {"amount": 12}}

    # LEGACY MODE: no source/source_id -> minimal dicts
    actions = diff_bets(current, desired)

    # Exact minimal dict must appear; no envelope keys should be present
    assert _has_exact(actions, {"action": "clear", "bet_type": "place_6"})
    assert any(a.get("action") == "set" and a.get("bet_type") == "place_6" for a in actions)

    # Ensure no 'source' key is present in legacy mode outputs
    assert all("source" not in a and "id" not in a and "notes" not in a for a in actions)


def test_diff_bets_envelope_mode_returns_action_envelopes():
    # Simple desired state: set place_6 to 6, place_8 to 6
    state = {"units": 3, "bubble": False, "point": 0, "on_comeout": True}
    event = {"on_comeout": True}
    cfg = {"level": 10, "bubble": False}
    template = {
        "place": {"6": "units*2", "8": "units*2"},  # raw 6, legalized stays >= increments
    }
    desired = render_template(template, state, event, cfg)
    current = {}

    # ENVELOPE MODE
    plan = diff_bets(current, desired, source="template", source_id="template:TestMode")

    assert _all_have_envelope(plan, source="template", id_prefix="template:TestMode")
    assert any(a.get("action") == "set" and a.get("bet_type") == "place_6" for a in plan)
    assert any(a.get("action") == "set" and a.get("bet_type") == "place_8" for a in plan)