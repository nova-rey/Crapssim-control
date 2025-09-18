# crapssim_control/controller.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .bet_types import normalize_bet_type
from .eval import evaluate as _eval
from .templates_rt import render_template, diff_bets  # runtime-safe template & diff


class _CtrlState:
    """
    Internal mutable control state the rules operate on.
    Tests (and rules shim) expect the following public attributes:
      - vars: Dict[str, Any]          # user variables (e.g., units, mode, etc.)
      - mode: str | None
      - point: int | None
      - on_comeout: bool
      - rolls_since_point: int
      - counters: Dict[str, Any]      # misc counters, incl. last_event
    """
    __slots__ = ("vars", "mode", "point", "on_comeout", "rolls_since_point", "counters")

    def __init__(self, initial_vars: Dict[str, Any] | None = None) -> None:
        self.vars: Dict[str, Any] = dict(initial_vars or {})
        self.mode: str | None = self.vars.get("mode")
        self.point: int | None = None
        self.on_comeout: bool = False
        self.rolls_since_point: int = 0
        self.counters: Dict[str, Any] = {
            "last_event": None,
            "points_established": 0,
            "seven_outs": 0,
            "number_frequencies": {n: 0 for n in (2, 3, 4, 5, 6, 8, 9, 10, 11, 12)},
        }


def _normalize_event(e: Dict[str, Any]) -> Dict[str, Any]:
    """Make a shallow, predictable copy of an event dict."""
    ev = dict(e or {})
    # normalize names used in tests/specs
    if "type" in ev and "event" not in ev:
        ev["event"] = ev["type"]
    if "bet_type" in ev and "bet" not in ev:
        ev["bet"] = ev["bet_type"]
    # bet names normalized
    if "bet" in ev and isinstance(ev["bet"], str):
        ev["bet"] = normalize_bet_type(ev["bet"])
    return ev


def _eval_env(ctrl: _CtrlState, ev: Dict[str, Any] | None) -> Dict[str, Any]:
    """Evaluation environment for expressions in spec rules."""
    # Safe builtins are provided by evaluate(); we only surface variables & counters here.
    ctx: Dict[str, Any] = {}
    # expose user variables directly
    ctx.update(ctrl.vars)
    # expose derived read-only state
    ctx["mode"] = ctrl.mode
    ctx["point"] = ctrl.point
    ctx["on_comeout"] = ctrl.on_comeout
    ctx["rolls_since_point"] = ctrl.rolls_since_point
    ctx["counters"] = ctrl.counters
    # current event (read-only)
    if ev:
        ctx["event"] = dict(ev)
    return ctx


class ControlStrategy:
    """
    Drives rule evaluation + template rendering and returns materialization plans.

    Public surface (used by tests):
      - __init__(spec, table_cfg=None)
      - handle_event(event_dict, current_bets_dict) -> List[Dict]
      - state_snapshot() -> Dict[str, Any]
    """

    def __init__(self, spec: Dict[str, Any], table_cfg: Dict[str, Any] | None = None) -> None:
        self._spec = spec or {}
        self._table_cfg = dict(self._spec.get("table") or {})
        self._table_cfg.update(table_cfg or {})

        # Initialize internal control state with variables from spec, if any.
        initial_vars = dict(self._spec.get("variables") or {})
        # A lot of tests depend on having a "mode" and other vars present here.
        self._ctrl = _CtrlState(initial_vars)

        # pre-cache default mode if present in variables
        if "mode" in initial_vars:
            self._ctrl.mode = initial_vars["mode"]

    # ------------------------------------------------------------------ helpers

    def _assign_var(self, name: str, rhs: str | int | float | bool | None, event: Dict[str, Any]) -> None:
        """
        Evaluate RHS in the read-only context, then write the resulting value
        *into* ctrl.vars[name]. This is the only place we mutate variables based
        on rule actions, and tests expect these writes to persist to vs.user.
        """
        # Compute the value in a read-only evaluation environment.
        value = _eval(rhs, _eval_env(self._ctrl, event)) if isinstance(rhs, str) else rhs

        # Special-case a few state fields which are not stored inside vars:
        if name == "point":
            # point is tracked as control state (int|None)
            self._ctrl.point = int(value) if value not in (None, False) else None
            return
        if name == "on_comeout":
            self._ctrl.on_comeout = bool(value)
            return
        if name == "rolls_since_point":
            self._ctrl.rolls_since_point = int(value or 0)
            return
        if name == "mode":
            # keep mode mirrored in both ctrl.mode and vars["mode"] for visibility
            m = str(value) if value is not None else None
            self._ctrl.mode = m
            if m is None:
                self._ctrl.vars.pop("mode", None)
            else:
                self._ctrl.vars["mode"] = m
            return

        # Default case: write to user variables bag (this is what VarStore reads).
        self._ctrl.vars[name] = value

    def _apply_template(self, mode_name: str, current_bets: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """Render bets from the template for the given mode and diff from current."""
        modes = self._spec.get("modes") or {}
        mode_def = modes.get(mode_name) or {}
        template = mode_def.get("template") or {}
        desired = render_template(template, self._ctrl.vars, self._table_cfg)
        plan = diff_bets(current_bets, desired)
        # keep the mode in state
        self._ctrl.mode = mode_name
        self._ctrl.vars["mode"] = mode_name
        return plan

    def _exec_action(self, act: Any, event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Execute one action from a rule. Returns a (possibly empty) plan delta list.
        Supported action forms:
          - str expressions:
              * "apply_template('Aggressive')"
              * assignments like "units = units + 10" or "rolls_since_point = 0"
          - dict actions for direct betting ops: {"action": "...", ...} (passed through)
        """
        if isinstance(act, dict):
            # Directly a plan instruction (set/clear/etc.). Normalize bet_type names.
            a = dict(act)
            if "bet_type" in a:
                a["bet_type"] = normalize_bet_type(a["bet_type"])
            return [a]

        if not isinstance(act, str):
            return []

        # apply_template('Mode')
        if act.startswith("apply_template("):
            # very small parser: apply_template('<name>')
            inside = act[len("apply_template("):].rstrip(")")
            mode_name = inside.strip().strip('"').strip("'")
            return self._apply_template(mode_name, current_bets)

        # Simple assignment: <name> = <expr>
        if "=" in act and "==" not in act and "!=" not in act and "<=" not in act and ">=" not in act:
            lhs, rhs = act.split("=", 1)
            name = lhs.strip()
            rhs_expr = rhs.strip()

            # Support "+=" and "-=" syntaxes by rewriting them to normal assignments.
            # (The tests sometimes author rules with 'units += 10', etc.)
            if name.endswith("+") or name.endswith("-"):
                # Not expected; ignore odd cases.
                pass
            elif name.endswith(("+", "-")):
                pass
            elif "+=" in act or "-=" in act:
                # Handle forms like "units += 10" or "units -= x"
                # Re-parse properly:
                if "+=" in act:
                    name2, inc = act.split("+=", 1)
                    name2 = name2.strip()
                    rhs_expr = f"{name2} + ({inc.strip()})"
                    name = name2
                else:
                    name2, dec = act.split("-=", 1)
                    name2 = name2.strip()
                    rhs_expr = f"{name2} - ({dec.strip()})"
                    name = name2

            self._assign_var(name, rhs_expr, event)
            return []

        # Otherwise: treat as a pure expression to evaluate for side-effects (usually none).
        _ = _eval(act, _eval_env(self._ctrl, event))
        return []

    # ------------------------------------------------------------------ main API

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Accepts an engine/craps event + current bets, returns a plan (list of actions).
        Mutates internal control state and variables per the spec rules.
        """
        ev = _normalize_event(event)
        self._ctrl.counters["last_event"] = ev.get("event")

        # state machine basics used by some templates/specs
        if ev.get("event") == "comeout":
            self._ctrl.on_comeout = True
            self._ctrl.point = None
            self._ctrl.rolls_since_point = 0

        elif ev.get("event") == "point_established":
            self._ctrl.on_comeout = False
            self._ctrl.point = int(ev.get("point") or 0)
            self._ctrl.rolls_since_point = 0
            self._ctrl.counters["points_established"] += 1

        elif ev.get("event") == "roll":
            total = int(ev.get("total") or 0)
            # frequency bookkeeping
            if total in self._ctrl.counters["number_frequencies"]:
                self._ctrl.counters["number_frequencies"][total] += 1
            # increment rolls after the point is on
            if self._ctrl.point:
                self._ctrl.rolls_since_point += 1

        elif ev.get("event") == "seven_out":
            self._ctrl.counters["seven_outs"] += 1
            self._ctrl.point = None
            self._ctrl.on_comeout = True  # returns to comeout
            self._ctrl.rolls_since_point = 0

        # Compute plan by walking the rule list and applying those whose "on" matches.
        plan: List[Dict[str, Any]] = []
        rules: List[Dict[str, Any]] = list(self._spec.get("rules") or [])
        for rule in rules:
            on = rule.get("on") or {}
            # normalize event key for the rule matcher
            on_ev = dict(on)
            if "type" in on_ev and "event" not in on_ev:
                on_ev["event"] = on_ev.pop("type")

            # quick match: all keys in 'on' must match the incoming event (after normalization)
            ok = True
            for k, v in on_ev.items():
                if k == "bet":  # event['bet'] already normalized
                    want = normalize_bet_type(v) if isinstance(v, str) else v
                    if ev.get("bet") != want:
                        ok = False
                        break
                else:
                    if ev.get(k) != v:
                        ok = False
                        break
            if not ok:
                continue

            # matched → run "do" block
            actions = rule.get("do") or []
            for act in actions:
                plan_delta = self._exec_action(act, ev, current_bets or {})
                if plan_delta:
                    plan.extend(plan_delta)

        return plan

    def state_snapshot(self) -> Dict[str, Any]:
        """Return a serializable snapshot used by tests and the shim in rules.py."""
        return {
            "vars": dict(self._ctrl.vars),
            "mode": self._ctrl.mode,
            "point": self._ctrl.point,
            "on_comeout": self._ctrl.on_comeout,
            "rolls_since_point": self._ctrl.rolls_since_point,
            "counters": {
                "last_event": self._ctrl.counters.get("last_event"),
                "points_established": int(self._ctrl.counters.get("points_established", 0)),
                "seven_outs": int(self._ctrl.counters.get("seven_outs", 0)),
                "number_frequencies": dict(self._ctrl.counters.get("number_frequencies", {})),
            },
        }