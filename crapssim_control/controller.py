# crapssim_control/controller.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .bet_types import normalize_bet_type  # imported in case callers rely on module side-effects
from .eval import evaluate as _eval
from .templates_rt import render_template, diff_bets


@dataclass
class _CtrlState:
    # user/system variables used by rules and templates
    vars: Dict[str, Any] = field(default_factory=dict)

    # runtime state tracked across events
    point: Optional[int] = None
    on_comeout: bool = True
    rolls_since_point: int = 0

    # book-keeping / counters
    counters: Dict[str, Any] = field(default_factory=lambda: {
        "last_event": None,
        "points_established": 0,
        "seven_outs": 0,
        "number_frequencies": {n: 0 for n in range(2, 13)},
    })

    # optional mode label (some specs use this to pick templates)
    mode: Optional[str] = None


def _eval_env(ctrl: _CtrlState, event: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build the evaluation environment for rules' mini-expressions.
    Only safe primitives/values are exposed (checked by the evaluator).
    """
    env: Dict[str, Any] = {}
    # flatten the variables so 'units', 'base_units', etc. are directly addressable
    env.update(ctrl.vars)
    # expose some read-only state
    env["point"] = ctrl.point if ctrl.point is not None else None
    env["on_comeout"] = ctrl.on_comeout
    env["rolls_since_point"] = ctrl.rolls_since_point
    env["counters"] = ctrl.counters
    if ctrl.mode is not None:
        env["mode"] = ctrl.mode
    # event read-only
    if event:
        env["event"] = dict(event)
    return env


class ControlStrategy:
    """
    Orchestrates:
      - state transitions from incoming events
      - rule actions (expressions and apply_template)
      - producing a concrete plan (list of action dicts) to reach desired bets
    """

    def __init__(self, spec: Dict[str, Any], *, table_cfg: Optional[Dict[str, Any]] = None):
        self._spec = spec or {}
        self._table_cfg = table_cfg or self._spec.get("table") or {}
        # seed control state with default variables
        variables = dict(self._spec.get("variables") or {})
        mode = variables.get("mode")
        self._ctrl = _CtrlState(vars=variables, mode=mode)

    # --- API used by tests/adapters -------------------------------------------------

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Dict] | None) -> List[Dict[str, Any]]:
        """
        Main entry: mutate internal state based on event, run rule actions,
        and return a plan (list of action dicts) describing how to update bets.
        """
        current_bets = current_bets or {}
        ev = dict(event or {})

        # normalize to always have both keys so rules can match on either
        if "event" not in ev and "type" in ev:
            ev["event"] = ev["type"]
        if "type" not in ev and "event" in ev:
            ev["type"] = ev["event"]

        # update state from this event (comeout/point/roll/seven_out)
        self._preprocess_event_state(ev)

        plan: List[Dict[str, Any]] = []

        # match and execute rules
        for rule in self._spec.get("rules", []):
            cond = rule.get("on", {})
            if self._event_matches(ev, cond):
                for act in rule.get("do", []):
                    plan_delta = self._exec_action(act, ev, current_bets)
                    if plan_delta:
                        for a in plan_delta:
                            _ensure_bet_keys(a)
                        plan.extend(plan_delta)

        return plan

    def state_snapshot(self) -> Dict[str, Any]:
        """
        Return a copy of observable control state (used by tests).
        """
        s = self._ctrl
        return {
            "point": s.point,
            "on_comeout": s.on_comeout,
            "rolls_since_point": s.rolls_since_point,
            "counters": _copy_nested(s.counters),
            "mode": s.mode,
            **dict(s.vars),
        }

    def update_bets(self, table: Any) -> None:
        """
        Adapter hook before each roll. Not required for tests -> no-op.
        """
        return

    def after_roll(self, table: Any, event: Dict[str, Any]) -> None:
        """
        Adapter hook after each roll/settlement. Not required for tests -> no-op.
        """
        return

    # --- internals ------------------------------------------------------------------

    def _preprocess_event_state(self, ev: Dict[str, Any]) -> None:
        """
        Update internal state fields (point, on_comeout, counters...) from incoming event.
        """
        s = self._ctrl
        ev_type = ev.get("type")

        if ev_type == "comeout":
            s.on_comeout = True
            s.point = None
            s.rolls_since_point = 0

        elif ev_type == "point_established":
            # set point, leave comeout
            if "point" in ev and ev["point"] is not None:
                s.point = int(ev["point"])
            else:
                # keep previous if missing; most callers provide it
                pass
            s.on_comeout = False
            s.rolls_since_point = 0
            s.counters["points_established"] += 1

        elif ev_type == "roll":
            total = int(ev.get("total") or 0)
            if 2 <= total <= 12:
                s.counters["number_frequencies"][total] += 1
            # increment only if a point is established (not on comeout)
            if s.point is not None and s.point != 0 and not s.on_comeout:
                s.rolls_since_point += 1

        elif ev_type == "seven_out":
            # reset to comeout state
            s.point = None
            s.on_comeout = True
            s.rolls_since_point = 0
            s.counters["seven_outs"] += 1

        # remember last event
        s.counters["last_event"] = ev_type

    def _event_matches(self, ev: Dict[str, Any], cond: Dict[str, Any]) -> bool:
        """
        Simple all-keys match against event dict. Keys not in cond are ignored.
        """
        if not cond:
            return False
        for k, v in cond.items():
            if ev.get(k) != v:
                return False
        return True

    def _exec_action(
        self,
        action: Any,
        event: Dict[str, Any],
        current_bets: Dict[str, Dict],
    ) -> List[Dict[str, Any]]:
        """
        Execute a single rule action. Supported:
          - "apply_template('ModeName')"
          - assignment-like expressions that mutate ctrl.vars, e.g. "units = units + 10"
            (and "+="/ "-=" syntactic sugar)
        Returns a plan delta (list of action dicts).
        """
        # 1) Template application
        if isinstance(action, str) and action.strip().startswith("apply_template"):
            # Extract parentheses payload safely and evaluate it in our env
            arg_expr = action.strip()[len("apply_template"):].strip()
            if not (arg_expr.startswith("(") and arg_expr.endswith(")")):
                raise ValueError(f"apply_template() requires a single string argument: {action}")
            name = _eval(arg_expr[1:-1], _eval_env(self._ctrl, event))
            if not isinstance(name, str):
                raise ValueError(f"apply_template() arg must evaluate to str, got {type(name).__name__}")
            return self._apply_template(name, current_bets, event)

        # 2) Variable mutation expression (assignment)
        if isinstance(action, str):
            expr = action.strip()

            # Support "+=" and "-=" forms by translating into pure assignment
            if "+=" in expr:
                lhs, rhs = expr.split("+=", 1)
                target = lhs.strip()
                rhs_eval = rhs.strip()
                expr = f"{target} = {target} + ({rhs_eval})"
            elif "-=" in expr:
                lhs, rhs = expr.split("-=", 1)
                target = lhs.strip()
                rhs_eval = rhs.strip()
                expr = f"{target} = {target} - ({rhs_eval})"

            # Handle "name = <expr>" (variables live in ctrl.vars)
            if "=" in expr:
                lhs, rhs = expr.split("=", 1)
                lhs = lhs.strip()
                rhs = rhs.strip()

                value = _eval(rhs, _eval_env(self._ctrl, event))
                self._ctrl.vars[lhs] = value
                return []

            # Otherwise just evaluate (no side effects expected)
            _ = _eval(expr, _eval_env(self._ctrl, event))
            return []

        # Unknown action type
        return []

    def _apply_template(
        self,
        name: str,
        current_bets: Dict[str, Dict],
        event: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Render a template by name and diff against current bets to create actions.
        Ensures each action carries both 'bet_type' (engine-facing) and 'bet' (rules shim).
        """
        tmpl_spec = (self._spec.get("modes") or {}).get(name, {}).get("template") or {}

        # NOTE: use positional call to match templates_rt.render_template signature
        rendered = render_template(
            tmpl_spec,
            self._ctrl.vars,
            self._table_cfg,
            self._ctrl.on_comeout,
            self._ctrl.point,
        )

        # produce plan versus current bets
        plan = diff_bets(current_bets, rendered)

        # normalize action dicts
        for a in plan:
            _ensure_bet_keys(a)

        # track mode (optional)
        self._ctrl.mode = name
        return plan


# --- helpers -----------------------------------------------------------------------


def _ensure_bet_keys(a: Dict[str, Any]) -> None:
    """
    Guarantee that each plan action dict has both:
      - 'bet_type': engine-style name (e.g. 'pass_line', 'field', 'place_6', ...)
      - 'bet'     : a string the tuple-intent shim can normalize (e.g. 'pass_line' or 'field')
    """
    bt = a.get("bet_type")
    b = a.get("bet")

    # Try common fallbacks used by some diff emitters
    if not bt:
        if isinstance(a.get("kind"), str):
            kind = a["kind"]
            num = a.get("number") or a.get("point")
            if kind == "pass":
                bt = "pass_line"
            elif kind == "field":
                bt = "field"
            elif kind == "place" and num in (4, 5, 6, 8, 9, 10):
                bt = f"place_{int(num)}"

    if bt and not b:
        b = bt
    if b and not bt:
        bt = b

    if not bt:
        bt = "unknown"
    if not b:
        b = bt

    a["bet_type"] = bt
    a["bet"] = b


def _copy_nested(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _copy_nested(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_copy_nested(v) for v in x]
    return x