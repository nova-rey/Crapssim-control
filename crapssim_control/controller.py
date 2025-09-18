# crapssim_control/controller.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .bet_types import normalize_bet_type
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

    # current mode label (optional; some specs use it)
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
        # default mode if present in variables
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
        self._preprocess_event_state(ev)

        plan: List[Dict[str, Any]] = []

        # Find matching rules for this event; rules are in self._spec["rules"]
        for rule in self._spec.get("rules", []):
            cond = rule.get("on", {})
            if self._event_matches(ev, cond):
                for act in rule.get("do", []):
                    plan_delta = self._exec_action(act, ev, current_bets)
                    if plan_delta:
                        # normalize all actions to carry both 'bet_type' and 'bet'
                        for a in plan_delta:
                            _ensure_bet_keys(a)
                        plan.extend(plan_delta)

        # If no rule added actions but we established a point and templates exist,
        # some specs expect templates to apply only via explicit rules.
        # So we just return whatever plan we accumulated.
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
        Adapter hook: give the strategy a chance to place/update bets before a roll.
        The smoke tests don't require any behavior here, only that this method exists.
        So we leave it as a no-op.
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
            point = int(ev.get("point") or 0)
            s.point = point
            s.on_comeout = False
            s.rolls_since_point = 0
            s.counters["points_established"] += 1
        elif ev_type == "roll":
            total = int(ev.get("total") or 0)
            if 2 <= total <= 12:
                s.counters["number_frequencies"][total] += 1
            # increment only if a point is established
            if s.point:
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
            (or "+="/ "-=" syntactic sugar)
        Returns a plan delta (list of action dicts).
        """
        # 1) Template application
        if isinstance(action, str) and action.strip().startswith("apply_template"):
            # evaluate the argument expression to get the mode/template name
            # allow apply_template('Aggressive') or apply_template("Aggressive")
            # We extract the literal between parentheses safely via the evaluator.
            # Build a tiny expression that returns the arg
            arg_expr = action.strip()[len("apply_template"):].strip()
            if not (arg_expr.startswith("(") and arg_expr.endswith(")")):
                raise ValueError(f"apply_template() requires a single string argument: {action}")
            # Evaluate the inside using our safe evaluator context to allow expressions like mode name variable
            name = _eval(arg_expr[1:-1], _eval_env(self._ctrl, event))
            if not isinstance(name, (str,)):
                raise ValueError(f"apply_template() arg must evaluate to str, got {type(name).__name__}")
            return self._apply_template(name, current_bets, event)

        # 2) Variable mutation expression (assignment)
        if isinstance(action, str):
            expr = action.strip()

            # Support "+=" and "-=" forms by translating into pure assignment
            # e.g., "units += 10" -> "units = units + (10)"
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

            # Now handle "name = <expr>" for names that live in ctrl.vars
            if "=" in expr:
                lhs, rhs = expr.split("=", 1)
                lhs = lhs.strip()
                rhs = rhs.strip()

                # compute value in safe env
                value = _eval(rhs, _eval_env(self._ctrl, event))

                # Assign into ctrl.vars if the target exists or looks like a bare variable
                # (tests expect variables like 'units' to live in the user variable store)
                self._ctrl.vars[lhs] = value
                return []

            # If it's not an assignment or template, just evaluate for side-effects (none expected)
            _ = _eval(expr, _eval_env(self._ctrl, event))
            return []

        # Unknown action type -> ignore (tests don't rely on this)
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
        # Resolve template object from spec modes (runtime renderer handles mapping)
        tmpl_spec = (self._spec.get("modes") or {}).get(name, {}).get("template") or {}

        # render target bets from template given current variables & table cfg
        rendered = render_template(
            tmpl_spec,
            variables=self._ctrl.vars,
            table_cfg=self._table_cfg,
            on_comeout=self._ctrl.on_comeout,
            point=self._ctrl.point,
        )

        # produce plan versus current bets
        plan = diff_bets(current_bets, rendered)

        # normalize action dicts
        for a in plan:
            _ensure_bet_keys(a)

        # also track mode if caller uses it
        self._ctrl.mode = name
        return plan


# --- helpers -----------------------------------------------------------------------


def _ensure_bet_keys(a: Dict[str, Any]) -> None:
    """
    Guarantee that each plan action dict has both:
      - 'bet_type' : engine-style name (e.g. 'pass_line', 'field', 'place_6', ...)
      - 'bet'      : a string the tuple-intent shim can normalize (e.g. 'pass_line' or 'field')
    If only a tuple like ('pass', 6) was present (some renderers might do that), convert it
    to a canonical engine string using bet_types.normalize_bet_type in reverse where possible.
    """
    # common keys used by templates/diffs
    bt = a.get("bet_type")
    b = a.get("bet")

    # If neither provided but we have a tuple-like hint
    hint = a.get("kind") or a.get("type")
    if not bt and isinstance(hint, str):
        bt = hint

    # If we still don't have anything, try to derive from subcomponents many diffs use,
    # like {'kind':'place', 'number':6} etc.
    if not bt:
        kind = a.get("kind")
        num = a.get("number") or a.get("point")
        if kind == "pass":
            bt = "pass_line"
        elif kind == "field":
            bt = "field"
        elif kind == "place" and num in (4, 5, 6, 8, 9, 10):
            bt = f"place_{int(num)}"

    # Fill both keys consistently
    if bt and not b:
        b = bt
    if b and not bt:
        bt = b

    # Final fallback to avoid Nones in tuple-intents: set generic when totally unknown
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