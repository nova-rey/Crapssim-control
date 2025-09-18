"""
rules.py -- compatibility shim around ControlStrategy

- render_template(...) proxies to templates_rt.render_template
- run_rules_for_event(...) builds a temporary ControlStrategy, transplants caller state,
  runs a single event, and returns a plan in legacy tuple form:
    ('pass', None, 'set', 10) / ('pass', None, 'clear') / ('place', 6, 'set', 12) ...
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from .controller import ControlStrategy
from .templates_rt import render_template as rt_render_template


def render_template(template: Dict, state: Dict, event: Dict, table_cfg: Dict | None = None) -> Dict[str, Dict]:
    return rt_render_template(template, state, event, table_cfg or {})


def _extract_vars_mode(ctrl_state: Any) -> tuple[Dict[str, Any], Any]:
    if hasattr(ctrl_state, "get"):  # dict-like
        v = dict(ctrl_state.get("vars") or ctrl_state.get("variables") or {})
        mode = v.get("mode", ctrl_state.get("mode"))
        return v, mode
    # VarStore-like object
    vars_obj = getattr(ctrl_state, "variables", None)
    v = dict(vars_obj) if isinstance(vars_obj, dict) else {}
    mode = v.get("mode", getattr(ctrl_state, "mode", None))
    return v, mode


def _normalize_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    ev = dict(ev or {})
    if "event" in ev and "type" not in ev:
        ev["type"] = ev["event"]
    if "type" in ev and "event" not in ev:
        ev["event"] = ev["type"]
    return ev


def _to_legacy_tuples(plan: List[Dict]) -> List[Tuple]:
    out: List[Tuple] = []
    for a in plan:
        kind = a.get("kind")
        number = a.get("number")
        action = a.get("action")
        if action == "set":
            out.append((kind, number, "set", a.get("amount")))
        elif action == "clear":
            out.append((kind, number, "clear"))
        else:
            out.append((kind, number, action))
    return out


def _write_back_state_like_varstore(ctrl_state: Any, snapshot: Dict[str, Any]) -> None:
    """Update VarStore-like objects with mutated variables/mode/point/flags."""
    # Prefer .user for "effective" variables if present
    user = getattr(ctrl_state, "user", None)
    if isinstance(user, dict):
        user.update(snapshot.get("vars", {}))
        if snapshot.get("mode") is not None:
            user["mode"] = snapshot["mode"]
    # Also reflect into .variables for completeness
    variables = getattr(ctrl_state, "variables", None)
    if isinstance(variables, dict):
        variables.update(snapshot.get("vars", {}))
        if snapshot.get("mode") is not None:
            variables["mode"] = snapshot["mode"]
    # Simple attributes if they exist
    for k in ("point", "on_comeout", "rolls_since_point"):
        if hasattr(ctrl_state, k):
            try:
                setattr(ctrl_state, k, snapshot.get(k))
            except Exception:
                pass


def run_rules_for_event(
    spec: Dict[str, Any],
    ctrl_state: Any,
    event: Dict[str, Any],
    current_bets: Dict[str, Dict] | None = None,
    table_cfg: Dict[str, Any] | None = None,
) -> List[Tuple]:
    cs = ControlStrategy(spec, table_cfg=table_cfg or spec.get("table") or {})

    # Transplant incoming state
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

    # Write back mutated control state for VarStore-like callers
    snapshot = cs.state_snapshot()
    try:
        if hasattr(ctrl_state, "update"):
            ctrl_state.update(snapshot)
        else:
            _write_back_state_like_varstore(ctrl_state, snapshot)
    except Exception:
        pass

    return _to_legacy_tuples(plan)