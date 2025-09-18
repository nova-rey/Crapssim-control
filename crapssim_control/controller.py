# crapssim_control/controller.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .eval import evaluate as _eval
from .templates_rt import render_template
from .utils import diff_bets


@dataclass
class _CtrlState:
    """Internal runtime state holder used to expose variables to the evaluator and rules."""
    vars: Dict[str, Any] = field(default_factory=dict)

    # table/hand state exposed to expressions
    on_comeout: bool = True
    point: Optional[int] = None
    rolls_since_point: int = 0
    mode: Optional[str] = None

    # some useful counters for richer strategies (optionally populated)
    counters: Dict[str, Any] = field(default_factory=lambda: {
        "number_frequencies": {i: 0 for i in range(2, 13)},
        "points_established": 0,
        "sevens_out": 0,
        "last_event": None,
    })


def _eval_env(ctrl: _CtrlState, event: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the evaluation environment for expressions."""
    env = {
        **ctrl.vars,
        "on_comeout": ctrl.on_comeout,
        "point": ctrl.point if ctrl.point else 0,
        "rolls_since_point": ctrl.rolls_since_point,
        "mode": ctrl.mode,
        "counters": ctrl.counters,
        "state": {
            "on_comeout": ctrl.on_comeout,
            "point": ctrl.point,
            "rolls_since_point": ctrl.rolls_since_point,
            "mode": ctrl.mode,
            "counters": ctrl.counters,
        },
    }
    if event:
        # mirror tests: expose both "event" and the event keys at top-level
        env["event"] = dict(event)
        for k, v in event.items():
            if k not in env:
                env[k] = v
    return env


def _normalize_action(a: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure each action carries engine-facing 'bet_type' and rules-facing 'bet'.
    Accepts variations from diff_bets/template rendering.
    """
    bet_type = a.get("bet_type") or a.get("bet") or a.get("kind")
    amount = a.get("amount") or a.get("value") or a.get("units") or 0
    res = dict(a)
    res["bet_type"] = bet_type
    res["bet"] = bet_type  # rules module expects 'bet'
    res["amount"] = amount
    return res


class ControlStrategy:
    """
    Rules-driven controller that turns game events into bet update plans.
    """

    def __init__(self, spec: Dict[str, Any]):
        self._spec = spec or {}

        # table config shim (bubble/level keys)
        tbl = self._spec.get("table") or {}
        self._table_cfg = {
            "bubble": bool(tbl.get("bubble", False)),
            "level": int(tbl.get("level", 5)),
        }

        # seed variables + default mode
        variables = dict((self._spec.get("variables") or {}))
        default_mode = variables.get("mode") or (self._spec.get("modes") and next(iter(self._spec["modes"].keys()))) or None

        self._ctrl = _CtrlState(vars=variables, mode=default_mode)

    # --- Public adapter hooks expected by tests/EngineAdapter

    def update_bets(self, table_like: Any) -> None:
        """EngineAdapter pre-roll hook: we don't auto-place here, rules drive placements via events."""
        # Intentionally a no-op; bets placed via explicit 'apply_template' actions on events.
        return

    def after_roll(self, table_like: Any, event: Dict[str, Any]) -> None:
        """EngineAdapter post-roll bookkeeping: update counters/frequencies."""
        total = event.get("total")
        if isinstance(total, int) and 2 <= total <= 12:
            self._ctrl.counters["number_frequencies"][total] += 1
        self._ctrl.counters["last_event"] = event.get("event") or event.get("type")

    def state_snapshot(self) -> Dict[str, Any]:
        """Lightweight state view used in tests."""
        return {
            "on_comeout": self._ctrl.on_comeout,
            "point": self._ctrl.point if self._ctrl.point else None,
            "rolls_since_point": self._ctrl.rolls_since_point,
            "mode": self._ctrl.mode,
            "counters": self._ctrl.counters,
        }

    # --- Core event handler used both by tests and rules shim

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict[str, Any]]:
        ev = dict(event)
        if "event" not in ev and "type" in ev:
            ev["event"] = ev["type"]
        if "type" not in ev and "event" in ev:
            ev["type"] = ev["event"]

        # state transitions based on event
        if ev["event"] == "comeout":
            self._ctrl.on_comeout = True
            self._ctrl.point = None
            self._ctrl.rolls_since_point = 0

        elif ev["event"] == "point_established":
            self._ctrl.on_comeout = False
            self._ctrl.point = int(ev.get("point") or 0) or None
            self._ctrl.rolls_since_point = 0
            self._ctrl.counters["points_established"] += 1

        elif ev["event"] == "roll":
            if not self._ctrl.on_comeout and self._ctrl.point:
                self._ctrl.rolls_since_point += 1

        elif ev["event"] == "seven_out":
            self._ctrl.on_comeout = True
            self._ctrl.point = None
            self._ctrl.rolls_since_point = 0
            self._ctrl.counters["sevens_out"] += 1

        # Run rules: for this simple controller, we execute the single matching rule list
        plan: List[Dict[str, Any]] = []
        for act in (self._spec.get("rules") or []):
            plan_delta = self._exec_action(act, ev, current_bets)
            if plan_delta:
                plan.extend(plan_delta)

        return plan

    # --- Helpers

    def _exec_action(self, act: Dict[str, Any], event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Execute one action descriptor into a set of bet update commands.
        Action schema mirrors tests/spec:
          - {"apply_template": "<name>"}
          - {"expr": "<python-ish expression>"}
        """
        if "apply_template" in act or act.get("do") == "apply_template":
            name = act["apply_template"] if "apply_template" in act else act.get("name") or act.get("value")
            return self._apply_template(name, current_bets, event)

        if "expr" in act:
            expr = act["expr"]

            # First, try to handle simple assignments/aug-assignments the evaluator disallows.
            if self._maybe_exec_assignment(expr, event):
                return []

            # Fall back to pure expression evaluation (no state mutation)
            _ = _eval(expr, _eval_env(self._ctrl, event))
            return []

        # Fallback: rule with explicit "do": string or list
        if "do" in act:
            cmds = act["do"]
            if isinstance(cmds, str):
                cmds = [cmds]

            out_plan: List[Dict[str, Any]] = []
            for cmd in cmds:
                if cmd.startswith("apply_template("):
                    # extract name inside quotes
                    name = cmd[len("apply_template("):].rstrip(")").strip().strip('"').strip("'")
                    out_plan.extend(self._apply_template(name, current_bets, event))
                else:
                    # assignment-friendly path
                    if not self._maybe_exec_assignment(cmd, event):
                        _ = _eval(cmd, _eval_env(self._ctrl, event))
            return out_plan

        return []

    def _maybe_exec_assignment(self, expr: str, event: Optional[Dict[str, Any]]) -> bool:
        """
        Support a tiny subset of statements used in specs: 'name = <expr>' and 'name += <expr>'.
        Returns True if handled (mutation performed), False otherwise.
        """
        s = expr.strip()
        op = None
        if "+=" in s:
            parts = s.split("+=", 1)
            op = "+="
        elif "=" in s:
            parts = s.split("=", 1)
            op = "="
        else:
            return False

        lhs, rhs = parts[0].strip(), parts[1].strip()
        if not lhs.isidentifier():
            return False  # not a simple name on LHS; let evaluator complain

        # evaluate RHS as a pure expression
        rhs_val = _eval(rhs, _eval_env(self._ctrl, event))

        # figure out current value if +=
        if op == "+=":
            cur = self._get_var_or_state(lhs)
            rhs_val = (cur or 0) + rhs_val

        # write back
        self._set_var_or_state(lhs, rhs_val)
        return True

    def _get_var_or_state(self, name: str) -> Any:
        if name == "rolls_since_point":
            return self._ctrl.rolls_since_point
        if name == "point":
            return self._ctrl.point
        if name == "on_comeout":
            return self._ctrl.on_comeout
        if name == "mode":
            # prefer explicit runtime mode, fall back to vars
            return self._ctrl.mode if self._ctrl.mode is not None else self._ctrl.vars.get("mode")
        # default to user vars
        return self._ctrl.vars.get(name)

    def _set_var_or_state(self, name: str, value: Any) -> None:
        if name == "rolls_since_point":
            self._ctrl.rolls_since_point = int(value)
            return
        if name == "point":
            self._ctrl.point = int(value) if value else None
            return
        if name == "on_comeout":
            self._ctrl.on_comeout = bool(value)
            return
        if name == "mode":
            self._ctrl.mode = value
            self._ctrl.vars["mode"] = value
            return
        # default to user vars
        self._ctrl.vars[name] = value

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

        # NOTE: use positional call to match templates_rt.render_template signature
        # Signature in this project is: render_template(template_spec, variables, table_cfg[, on_comeout/point bundled])
        # Our runtime state supplies variables and table config; on_comeout/point can be derived downstream.
        rendered = render_template(
            tmpl_spec,
            self._ctrl.vars,
            self._table_cfg,
        )

        # Diff against current to produce actions
        actions = diff_bets(current_bets or {}, rendered or {})

        # Normalize each action to include both 'bet_type' and 'bet'
        return [_normalize_action(a if isinstance(a, dict) else {
            # some diff_bets variants return tuples; coerce to dict best-effort
            "action": a[0] if len(a) > 0 else None,
            "amount": a[1] if len(a) > 1 else None,
            "bet_type": a[2] if len(a) > 2 else None,
        }) for a in actions]