# crapssim_control/controller.py

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

from .templates import render_template
from .eval import evaluate as _eval


# Minimal mapping so rules-facing code can recognize logical bet names.
# Extend here if future tests rely on more mappings.
_ENGINE_TO_RULES_BET = {
    "pass_line": "pass",
    "dont_pass": "dont_pass",
    "field": "field",
}


def _rules_bet_for(bet_type: str) -> str:
    # Best-effort mapping; fall back to original name.
    return _ENGINE_TO_RULES_BET.get(bet_type, bet_type)


def _diff_bets_to_actions(
    current: Dict[str, Any],
    desired: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Produce a list of action dicts to transform current -> desired.

    Each action has BOTH:
      - engine-facing: 'bet_type'
      - rules-facing:  'bet'        (for tests that expect a logical name)
    And: 'action' in {'set', 'remove'}, and 'amount' (number for set, 0 for remove).
    """
    actions: List[Dict[str, Any]] = []

    # Normalize amounts where desired is like {"pass_line": 10, ...}
    def _amt(v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        # Allow objects like {'amount': 10}
        if isinstance(v, dict) and "amount" in v and isinstance(v["amount"], (int, float)):
            return float(v["amount"])
        return None

    # Build simple amount maps
    curr_amt = {k: _amt(v) for k, v in (current or {}).items()}
    want_amt = {k: _amt(v) for k, v in (desired or {}).items()}

    # Set or update changed bets
    for bet_type, amount in want_amt.items():
        if amount is None:
            continue
        if curr_amt.get(bet_type) != amount:
            actions.append(
                {
                    "action": "set",
                    "bet_type": bet_type,
                    "bet": _rules_bet_for(bet_type),
                    "amount": amount,
                }
            )

    # Remove bets that are no longer present
    for bet_type in (curr_amt.keys() - want_amt.keys()):
        actions.append(
            {
                "action": "remove",
                "bet_type": bet_type,
                "bet": _rules_bet_for(bet_type),
                "amount": 0.0,
            }
        )

    return actions


class _CtrlState:
    """
    Small holder for controller runtime state that tests expect:
      - mode
      - vars (user variables)
      - on_comeout
      - point
      - counters incl. rolls_since_point
    """

    def __init__(self, variables: Dict[str, Any], table_cfg: Dict[str, Any]):
        self.vars: Dict[str, Any] = dict(variables or {})
        self.mode: str = (self.vars.get("mode") or "Main")
        self.on_comeout: bool = True  # start at comeout until a point is set
        self.point: Optional[int] = None
        self.table_cfg: Dict[str, Any] = dict(table_cfg or {})

        # bonus counters used by tests
        self.counters: Dict[str, Any] = {
            "seven_outs": 0,
            "points_established": 0,
            "number_frequencies": {n: 0 for n in range(2, 13)},
            "last_event": None,
        }

        # explicit helper counters
        self.rolls_since_point: int = 0


def _eval_env(ctrl: _CtrlState, event: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    # Expose a simple flat namespace for the mini-eval engine.
    env = dict(ctrl.vars)
    env.update(
        {
            "mode": ctrl.mode,
            "on_comeout": ctrl.on_comeout,
            "point": ctrl.point,
            "table": ctrl.table_cfg,
            "rolls_since_point": ctrl.rolls_since_point,
            "counters": ctrl.counters,
            "event": event,
        }
    )
    return env


class ControlStrategy:
    """
    Event-driven controller that:
      - Tracks mode/point/comeout/counters
      - Renders templates into target bet states
      - Diffs against current bets to produce action plans
      - Offers adapter hooks: update_bets() and after_roll()
    """

    def __init__(self, spec: Dict[str, Any]):
        self._spec = dict(spec or {})
        self._table_cfg = dict(self._spec.get("table") or {})
        self._ctrl = _CtrlState(self._spec.get("variables") or {}, self._table_cfg)

    # -------------------------
    # Public adapter-facing API
    # -------------------------
    def update_bets(self, table_like: Any) -> None:
        """
        Called before each roll by EngineAdapter to let the strategy place/adjust bets.
        We synthesize a 'comeout' or 'roll' event depending on current state.
        """
        ev_type = "comeout" if self._ctrl.on_comeout else "roll"
        _ = self.handle_event({"type": ev_type, "event": ev_type}, current_bets=_safe_collect_bets(table_like))

    def after_roll(self, table_like: Any, event: Dict[str, Any]) -> None:
        """
        Called after settlements to let the strategy update counters/state derived from the event.
        """
        et = event.get("event")
        if et == "point_established":
            self._ctrl.on_comeout = False
            self._ctrl.point = event.get("point")
            self._ctrl.rolls_since_point = 0
            self._ctrl.counters["points_established"] += 1
        elif et == "seven_out":
            self._ctrl.on_comeout = True
            self._ctrl.point = None
            self._ctrl.rolls_since_point = 0
            self._ctrl.counters["seven_outs"] += 1
        elif et == "roll":
            total = event.get("total")
            if isinstance(total, int):
                self._ctrl.counters["number_frequencies"][total] = (
                    self._ctrl.counters["number_frequencies"].get(total, 0) + 1
                )
            # Only increment between point and seven-out
            if self._ctrl.point is not None:
                self._ctrl.rolls_since_point += 1

        self._ctrl.counters["last_event"] = et

    # -------------------------
    # Test/driver API
    # -------------------------
    def state_snapshot(self) -> Dict[str, Any]:
        return {
            "mode": self._ctrl.mode,
            "on_comeout": self._ctrl.on_comeout,
            "point": self._ctrl.point,
            "rolls_since_point": self._ctrl.rolls_since_point,
            "counters": self._ctrl.counters,
            "vars": dict(self._ctrl.vars),
        }

    def handle_event(
        self,
        ev: Dict[str, Any],
        current_bets: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Core event handler. Translates spec rules to actions via:
          - updating internal state flags for high-level events
          - running 'do' clauses (eval of simple assignments and apply_template)
          - returning an action plan (list of dicts)
        """
        event = dict(ev or {})
        event.setdefault("event", event.get("type"))

        # Interpret high-level state flips here, mirroring after_roll for tests that drive directly
        et = event.get("event")
        if et == "comeout":
            self._ctrl.on_comeout = True
            self._ctrl.point = None
        elif et == "point_established":
            self._ctrl.on_comeout = False
            self._ctrl.point = event.get("point")
            self._ctrl.rolls_since_point = 0
            self._ctrl.counters["points_established"] += 1
        elif et == "seven_out":
            self._ctrl.on_comeout = True
            self._ctrl.point = None
            self._ctrl.rolls_since_point = 0
            self._ctrl.counters["seven_outs"] += 1
        elif et == "roll":
            # Only count rolls after point is on
            if self._ctrl.point is not None:
                self._ctrl.rolls_since_point += 1

        # Find rules that match this event
        rules: List[Dict[str, Any]] = self._spec.get("rules") or []
        plan: List[Dict[str, Any]] = []

        for rule in rules:
            on = rule.get("on") or {}
            if not _matches(on, event):
                continue

            for expr in rule.get("do") or []:
                # apply_template('ModeName') is the only function-like clause we support here
                if isinstance(expr, str) and expr.startswith("apply_template(") and expr.endswith(")"):
                    mode_name = expr[len("apply_template(") : -1].strip().strip("'\"")
                    plan.extend(self._apply_template(mode_name, current_bets or {}, event))
                else:
                    # treat as simple expression (assignments like 'units = 10' or 'units += 10', etc.)
                    # use our safe/eager eval shim
                    env = _eval_env(self._ctrl, None)  # expressions aren't event-aware in tests
                    result = _eval(expr, env)

                    # Pull back any mutated names we care about (units, mode, rolls_since_point, etc.)
                    for k in list(self._ctrl.vars.keys()):
                        if k in env:
                            self._ctrl.vars[k] = env[k]
                    # also pull top-level keys we expose
                    for k in ("mode", "rolls_since_point"):
                        if k in env:
                            setattr(self._ctrl, k, env[k])

        return plan

    # -------------------------
    # Internals
    # -------------------------
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
        # Resolve template object from spec modes
        tmpl_spec = (self._spec.get("modes") or {}).get(name, {}).get("template") or {}

        # templates.render_template signature in this repo is (template, variables, table_cfg [, point?]).
        # Older/newer variants differ; we support both by trying with/without point.
        variables = self._ctrl.vars
        table_cfg = self._table_cfg

        try:
            # Try with point as the 4th positional arg (newer tests sometimes pass this)
            rendered = render_template(tmpl_spec, variables, table_cfg, self._ctrl.point)
        except TypeError:
            # Fallback to the classic 3-arg form
            rendered = render_template(tmpl_spec, variables, table_cfg)

        actions = _diff_bets_to_actions(current_bets or {}, rendered or {})
        return actions


def _matches(on: Dict[str, Any], event: Dict[str, Any]) -> bool:
    """
    Rule match helper: every key in 'on' must be present and equal in event.
    """
    for k, v in (on or {}).items():
        if event.get(k) != v:
            return False
    return True


def _safe_collect_bets(table_like: Any) -> Dict[str, Any]:
    """
    Adapter helper: best-effort extraction of a player's current bets
    as a mapping bet_type -> amount. The fake engine in tests only needs simple shapes.
    """
    # Try table_like.get_player_bets() first
    if hasattr(table_like, "get_player_bets"):
        try:
            bets = table_like.get_player_bets()
            if isinstance(bets, dict):
                return bets
        except Exception:
            pass

    # Try table_like.player.bets list of objects with kind/amount
    player = getattr(table_like, "player", None)
    if player is not None:
        bets_list = getattr(player, "bets", None)
        if isinstance(bets_list, list):
            out: Dict[str, Any] = {}
            for b in bets_list:
                kind = getattr(b, "kind", None) or getattr(b, "bet_type", None)
                amt = getattr(b, "amount", None)
                if kind and isinstance(amt, (int, float)):
                    out[str(kind)] = float(amt)
            return out

    return {}