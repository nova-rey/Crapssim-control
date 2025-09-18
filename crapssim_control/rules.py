"""
rules.py -- Batch 15: rule runner (kept backward-compatible)

Exports:
  - run_rules_for_event(spec, ctrl_state_like_dict, event, current_bets, table_cfg) -> actions
  - render_template(template, state, event, table_cfg) -> desired_bets
    (this thin wrapper proxies to templates_rt.render_template for back-compat)
"""

from __future__ import annotations

from typing import Any, Dict, List
from .controller import ControlStrategy
from .templates_rt import render_template as rt_render_template


def render_template(template: Dict, state: Dict, event: Dict, table_cfg: Dict | None = None) -> Dict[str, Dict]:
    """
    Back-compat wrapper used by older callers/tests.
    """
    # We don't need ctrl state here; templates_rt is pure.
    return rt_render_template(template, state, event, table_cfg or {})


def run_rules_for_event(
    spec: Dict[str, Any],
    ctrl_state: Dict[str, Any],
    event: Dict[str, Any],
    current_bets: Dict[str, Dict] | None = None,
    table_cfg: Dict[str, Any] | None = None,
) -> List[Dict]:
    """
    Back-compat API: execute rules for one event given an external control state dict.

    ctrl_state is expected to have keys like: vars, mode, point, on_comeout, rolls_since_point
    We instantiate a temporary ControlStrategy, transplant state, run once, then return plan.
    """
    cs = ControlStrategy(spec, table_cfg=table_cfg or spec.get("table") or {})
    # transplant incoming control-ish fields
    s = cs._ctrl  # internal but intentional for this shim
    s.vars = dict(ctrl_state.get("vars") or {})
    s.mode = ctrl_state.get("mode")
    s.point = ctrl_state.get("point")
    s.on_comeout = bool(ctrl_state.get("on_comeout", False))
    s.rolls_since_point = int(ctrl_state.get("rolls_since_point", 0))

    plan = cs.handle_event(event or {}, current_bets or {})
    # push back the updates so caller can persist
    ctrl_state.update(cs.state_snapshot())
    return plan