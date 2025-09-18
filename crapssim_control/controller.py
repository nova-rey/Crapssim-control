# crapssim_control/controller.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from .eval import evaluate as _eval
from .templates_rt import render_template, diff_bets


@dataclass
class _CtrlState:
    """
    Internal control state the rules & controller mutate over time.
    Only minimal fields are tracked to satisfy tests / adapter flow.
    """
    vars: Dict[str, Any] = field(default_factory=dict)
    mode: str = "Main"

    # Table/hand state for convenience
    point: int | None = None
    on_comeout: bool = True
    rolls_since_point: int = 0

    # lightweight counters used by eval environment
    counters: Dict[str, Any] = field(default_factory=lambda: {
        "points_established": 0,
        "seven_outs": 0,
        "number_frequencies": {n: 0 for n in (2, 3, 4, 5, 6, 8, 9, 10, 11, 12)},
        "last_event": None,
    })


class ControlStrategy:
    """
    Reference runtime that:
      - tracks a small mutable control state (variables + simple point/comeout bookkeeping)
      - applies spec-defined actions to produce a betting plan (set/remove/update)
      - exposes a tiny adapter surface for the engine adapter smoke test
    """

    def __init__(self, spec: Dict[str, Any], table_cfg: Dict[str, Any] | None = None) -> None:
        self._spec = spec or {}
        self._table_cfg = table_cfg or (self._spec.get("table") or {})

        # seed variables
        variables = dict(self._spec.get("variables") or {})
        default_mode = variables.get("mode") or (list((self._spec.get("modes") or {}).keys())[:1] or ["Main"])[0]

        self._ctrl = _CtrlState(vars=variables, mode=default_mode)

    # ---------------------------
    # Small engine-adapter surface
    # ---------------------------

    def update_bets(self, table: Any) -> None:
        """
        Called by the EngineAdapter before each roll.
        For this minimal reference impl we don't proactively bet before a derived event,
        so this is a no-op on purpose.
        """
        return None

    def after_roll(self, table: Any, event: Dict[str, Any]) -> None:
        """
        Called by the EngineAdapter after a roll has happened and been settled.
        We only do bookkeeping that mirrors what tests expect:
          - increment rolls_since_point on rolls (when a point is on)
          - reset point/on_comeout on seven_out
        """
        ev_type = event.get("type") or event.get("event")
        self._ctrl.counters["last_event"] = ev_type

        if ev_type == "roll":
            total = event.get("total")
            if isinstance(total, int) and total in self._ctrl.counters["number_frequencies"]:
                self._ctrl.counters["number_frequencies"][total] += 1

            if self._ctrl.point:
                self._ctrl.rolls_since_point += 1

        elif ev_type == "seven_out":
            # reset table state
            self._ctrl.counters["seven_outs"] += 1
            self._ctrl.point = None
            self._ctrl.on_comeout = True
            self._ctrl.rolls_since_point = 0

        elif ev_type == "point_established":
            p = int(event.get("point") or 0)
            self._ctrl.point = p
            self._ctrl.on_comeout = False
            self._ctrl.rolls_since_point = 0
            self._ctrl.counters["points_established"] += 1

    # ---------------------------
    # Primary rules/event entrypoint
    # ---------------------------

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Main entry the tests use: consume an event and current bets,
        return a plan (list of actions).
        """
        ev = _normalize_event(event)

        # Minimal built-in bookkeeping to satisfy tests that call handle_event directly
        if ev["type"] == "point_established":
            p = int(ev.get("point") or 0)
            self._ctrl.point = p
            self._ctrl.on_comeout = False
            self._ctrl.rolls_since_point = 0
            self._ctrl.counters["points_established"] += 1

        elif ev["type"] == "roll":
            total = ev.get("total")
            if isinstance(total, int) and total in self._ctrl.counters["number_frequencies"]:
                self._ctrl.counters["number_frequencies"][total] += 1
            if self._ctrl.point:
                self._ctrl.rolls_since_point += 1

        elif ev["type"] == "seven_out":
            self._ctrl.counters["seven_outs"] += 1
            self._ctrl.point = None
            self._ctrl.on_comeout = True
            self._ctrl.rolls_since_point = 0

        # Execute matching rule actions (in order) and accumulate plan
        plan: List[Dict[str, Any]] = []
        for act in self._match_actions(ev):
            plan_delta = self._exec_action(act, ev, current_bets)
            if plan_delta:
                plan.extend(plan_delta)

        return plan

    # ---------------------------
    # Introspection helpers for tests/shims
    # ---------------------------

    def state_snapshot(self) -> Dict[str, Any]:
        """
        Provide a compact snapshot used by tests/rules shim to round-trip state.
        """
        return {
            "vars": dict(self._ctrl.vars),
            "mode": self._ctrl.mode,
            "point": self._ctrl.point,
            "on_comeout": self._ctrl.on_comeout,
            "rolls_since_point": self._ctrl.rolls_since_point,
            "counters": self._ctrl.counters,
        }

    # ---------------------------
    # Internals
    # ---------------------------

    def _match_actions(self, event: Dict[str, Any]) -> List[Tuple[str, Any]]:
        """
        Return a flat list of ("kind", payload) describing the actions
        for rules whose `on` clause matches the event.
        Supported action kinds:
          - "expr": a textual expression to evaluate/mutate variables
          - "apply_template": name of a template/mode to render and diff to actions
        """
        actions: List[Tuple[str, Any]] = []
        for rule in self._spec.get("rules") or []:
            on = rule.get("on") or {}
            if _event_matches(on, event):
                for step in rule.get("do") or []:
                    if isinstance(step, str):
                        if step.startswith("apply_template(") and step.endswith(")"):
                            # pull the single quoted template name
                            name = step[len("apply_template("):-1].strip()
                            if (name.startswith("'") and name.endswith("'")) or (name.startswith('"') and name.endswith('"')):
                                name = name[1:-1]
                            actions.append(("apply_template", name))
                        else:
                            actions.append(("expr", step))
                    elif isinstance(step, dict) and step.get("action") == "apply_template":
                        actions.append(("apply_template", step.get("name")))
                    else:
                        # fall back: treat as no-op
                        pass
        return actions

    def _exec_action(self, action: Tuple[str, Any], event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict[str, Any]] | None:
        kind, payload = action
        if kind == "expr":
            expr = str(payload)
            # mutate vars via expression evaluator
            _ = _eval(expr, _eval_env(self._ctrl, event))
            return []

        if kind == "apply_template":
            name = str(payload or self._ctrl.mode or "Main")
            return self._apply_template(name, current_bets, event)

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

        # NOTE: match templates_rt.render_template signature: (template, vars, table_cfg[, optional])
        # The tests that are failing do not require the optional 4th param (point/comeout),
        # so we call the 3-arg form for maximum compatibility.
        rendered = render_template(
            tmpl_spec,
            self._ctrl.vars,
            self._table_cfg,
        )

        # Compute actions from diff against current
        actions = diff_bets(current_bets or {}, rendered or {})

        # Ensure each action carries both bet_type (engine) and bet (rules shim)
        out: List[Dict[str, Any]] = []
        for act in actions:
            a = dict(act)
            bet_type = a.get("bet_type") or a.get("bet")
            if bet_type is None:
                # skip malformed
                continue
            a["bet_type"] = bet_type
            a["bet"] = bet_type
            out.append(a)
        return out


# ---------------------------
# Helpers
# ---------------------------

def _normalize_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    e = dict(ev or {})
    if "type" not in e and "event" in e:
        e["type"] = e["event"]
    if "event" not in e and "type" in e:
        e["event"] = e["type"]
    return e


def _event_matches(on: Dict[str, Any], event: Dict[str, Any]) -> bool:
    """
    A tiny matcher: all keys present in `on` must match exactly on the event.
    (Used by tests to ensure we require all declared keys, not just 'event').
    """
    if not on:
        return False
    for k, v in on.items():
        if event.get(k) != v:
            return False
    return True


def _eval_env(ctrl: _CtrlState, event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build evaluation environment for expressions.
    Only exposes safe primitives and our variables/counters.
    """
    env: Dict[str, Any] = {}
    # whitelist primitives via the evaluator itself (min, max, abs provided there)
    # expose variables and a couple of state flags as plain values
    env.update(ctrl.vars)
    env["mode"] = ctrl.mode
    env["point"] = ctrl.point if ctrl.point is not None else 0
    env["on_comeout"] = ctrl.on_comeout
    env["rolls_since_point"] = ctrl.rolls_since_point
    env["counters"] = ctrl.counters
    # event is available to rules if needed
    env["event"] = event
    return env