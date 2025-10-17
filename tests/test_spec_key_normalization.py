"""Tests for deprecated spec key normalization shim."""

from __future__ import annotations

from copy import deepcopy

from crapssim_control.controller import ControlStrategy
from crapssim_control.spec_loader import normalize_deprecated_keys


def _base_spec():
    return {
        "variables": {"units": 5},
        "modes": {"Main": {"template": {"pass": "units"}}},
        "rules": [],
    }


def test_migrate_when_new_missing():
    spec = _base_spec()
    spec["odds_working_on_comeout"] = True

    normalized, deprecations = normalize_deprecated_keys(spec)

    assert normalized.get("working_on_comeout") is True
    assert "odds_working_on_comeout" not in normalized
    assert deprecations == [
        {"old": "odds_working_on_comeout", "new": "working_on_comeout", "action": "migrated"}
    ]

    ctrl = ControlStrategy(deepcopy(normalized), spec_deprecations=deprecations)
    report = ctrl.generate_report()
    assert report["metadata"]["deprecations"] == deprecations


def test_prefer_new_when_both():
    spec = _base_spec()
    spec["working_on_comeout"] = False
    spec["odds_working_on_comeout"] = True

    normalized, deprecations = normalize_deprecated_keys(spec)

    assert normalized.get("working_on_comeout") is False
    assert "odds_working_on_comeout" not in normalized
    assert deprecations == [
        {
            "old": "odds_working_on_comeout",
            "new": "working_on_comeout",
            "action": "kept_new_dropped_old",
        }
    ]

    ctrl = ControlStrategy(deepcopy(normalized), spec_deprecations=deprecations)
    report = ctrl.generate_report()
    assert report["metadata"]["deprecations"] == deprecations


def test_no_op_when_clean():
    spec = _base_spec()

    normalized, deprecations = normalize_deprecated_keys(spec)

    assert deprecations == []
    assert "working_on_comeout" not in normalized

    ctrl = ControlStrategy(deepcopy(normalized))
    report = ctrl.generate_report()
    assert report["metadata"].get("deprecations") == []
