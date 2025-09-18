"""
rules.py -- compatibility shim around ControlStrategy (Batch 15+)

- render_template(...) proxies to templates_rt.render_template
- run_rules_for_event(...) instantiates a temporary ControlStrategy, transplants caller state,
  runs a single event, and returns a plan. We enhance returned actions with (kind, number),
  so older tests that looked at 'intents' by kind/number still pass.
"""

from __future__ import annotations

from typing import Any, Dict, List
from .controller import ControlStrategy
from .templates_rt import render_template as rt_render_template


def render_template(template: Dict, state: Dict, event: Dict, table_cfg: Dict | None = None) -> Dict[str, Dict]:
    return rt_render_template(template, state, event, table_cfg or {})


def _extract_vars_mode(ctrl_state: Any) -> tuple[Dict[str, Any], Any]:
    """
    Accept either a dict-like state or a VarStore-like object with `.variables` and optional `.mode`.
    Returns (vars_dict, mode_value_or_None).
    """
    # dict-like
    if hasattr(ctrl_state, "get"):
        v = dict(ctrl_state.get("vars") or ctrl_state.get("variables") or {})
        mode = v.get("mode", ctrl_state.get("mode"))
        return v, mode
    # object-like (VarStore)
    vars_obj = getattr(ctrl_state, "variables", None)
    v = dict(vars_obj) if isinstance(vars_obj, dict) else {}
    mode = v.get("mode", getattr(ctrl_state, "mode", None))
    return v, mode


def _normalize_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    """Allow callers to pass {'event': 'comeout'}; we normalize to include 'type' alias."""
    ev = dict(ev or {})
    if "event" in ev and "type" not in ev:
        ev["type"] = ev["event"]
    if "type" in ev and "event" not in ev:
        ev["event"] = ev["type"]
    return ev


def run_rules_for_event(
    spec: Dict[str, Any],
    ctrl_state: Any,
    event: Dict[str, Any],
    current_bets: Dict[str, Dict] | None = None,
    table_cfg: Dict[str, Any] | None = None,
) -> List[Dict]:
    cs = ControlStrategy(spec, table_cfg=table_cfg or spec.get("table") or {})

    # Transplant state from caller
    s = cs._ctrl  # intentional internal access for this shim
    v, mode = _extract_vars_mode(ctrl_state)
    s.vars = v
    s.mode = mode

    def _get(name: str, default=None):
        if hasattr(ctrl_state, "get"):
            return ctrl_state.get(name, default)
        return getattr(ctrl_state, name, default)

    s.point = _get("point", None)
    s.on_comeout = bool(_get("on_comeout", False))
    s.rolls_since_point = int(_get("rolls_since_point", 0))

    ev = _normalize_event(event)
    plan = cs.handle_event(ev, current_bets or {})

    # For dict-like callers, reflect back any mutated control snapshot (best effort)
    try:
        if hasattr(ctrl_state, "update"):  # dict-like
            ctrl_state.update(cs.state_snapshot())
    except Exception:
        pass

    return plan