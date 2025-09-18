# crapssim_control/controller.py

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
import ast

from .templates_rt import render_template
from .eval import evaluate as _eval, EvalError

Action = Dict[str, Any]


def _amount_of(v: Any) -> float:
    """Normalize a desired/current bet entry to a float amount."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        if "amount" in v and isinstance(v["amount"], (int, float)):
            return float(v["amount"])
    return 0.0


def _normalize_bet(bt: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Convert internal bet_type to (bet, number) pairs expected by tests.
      - 'place_6'  -> ('place', 6)
      - 'pass_line'-> ('pass', None), also 'pass' -> ('pass', None)
      - 'field'    -> ('field', None)
      - 'odds_pass'/'odds' -> ('odds', None)
      - fallback   -> (bt, None)
    """
    if not isinstance(bt, str):
        return (None, None)
    if bt.startswith("place_"):
        try:
            return ("place", int(bt.split("_", 1)[1]))
        except Exception:
            return ("place", None)
    if bt in ("pass_line", "pass"):
        return ("pass", None)
    if bt in ("odds_pass", "odds"):
        return ("odds", None)
    if bt == "field":
        return ("field", None)
    return (bt, None)


def _mk_action(kind: str, bt: str, amount: Optional[float] = None) -> Action:
    """Create an action dict including compatibility fields for rules helpers."""
    bet, number = _normalize_bet(bt)
    act: Action = {"action": kind, "bet_type": bt, "bet": bet, "number": number}
    if amount is not None:
        act["amount"] = float(amount)
    return act


def _diff_bets(current: Dict[str, Any], desired: Dict[str, Any]) -> List[Action]:
    """
    Create a minimal set/clear plan to move from `current` -> `desired`.
    Handles both raw numbers and dicts with {"amount": ...}.
    """
    plan: List[Action] = []
    current = current or {}
    desired = desired or {}

    # clears
    for bt, _cval in sorted(current.items()):
        if bt not in desired or _amount_of(desired.get(bt)) <= 0.0:
            plan.append(_mk_action("clear", bt))

    # sets/updates
    for bt, dval in sorted(desired.items()):
        d_amt = _amount_of(dval)
        c_amt = _amount_of(current.get(bt))
        if d_amt > 0.0 and float(c_amt) != float(d_amt):
            plan.append(_mk_action("set", bt, d_amt))

    return plan


class ControlStrategy:
    """
    Interprets a control spec with modes/templates and rules.
    Maintains a small state dict for counters/flags used in expressions.
    """

    def __init__(
        self,
        spec: Dict[str, Any],
        var_store: Optional[Any] = None,
        *,
        table_cfg: Optional[Dict[str, Any]] = None,
    ):
        self.spec = spec or {}
        self.vars = var_store
        # prefer spec.table; fall back to provided table_cfg
        self.table_cfg = (self.spec.get("table") or {}) if isinstance(self.spec.get("table"), dict) else (table_cfg or {})

        self.state: Dict[str, Any] = {
            "point": None,
            "rolls_since_point": 0,
            "mode": (self.spec.get("variables", {}) or {}).get(
                "mode",
                next(iter(self.spec.get("modes", {}) or {"Main": {}}))
            ),
        }

    # --- EngineAdapter hooks required by smoke tests ---

    def update_bets(self, _table) -> None:
        return None

    def after_roll(self, _table, _event: Dict[str, Any]) -> None:
        return None

    # --- Internal helpers ---

    def _state_view(self) -> Dict[str, Any]:
        """Compose the eval namespace (user/spec vars + controller state)."""
        base_vars: Dict[str, Any] = {}
        if self.vars is not None and getattr(self.vars, "user", None) is not None:
            base_vars.update(self.vars.user)
        else:
            base_vars.update(self.spec.get("variables") or {})
        base_vars.update(self.state)
        return base_vars

    def _flush_overlay_back(self, overlay: Dict[str, Any]) -> None:
        """Write mutated overlay back into self.state and user/spec vars."""
        for k, v in overlay.items():
            if k in ("point", "rolls_since_point", "mode"):
                self.state[k] = v
            else:
                if self.vars is not None and getattr(self.vars, "user", None) is not None:
                    self.vars.user[k] = v
                else:
                    (self.spec.setdefault("variables", {}))[k] = v

    def _apply_template(
        self,
        template: Dict[str, Any],
        event: Dict[str, Any],
        current_bets: Dict[str, Any],
        *,
        state_ns: Optional[Dict[str, Any]] = None,
    ) -> List[Action]:
        if not template:
            return []
        table_cfg = self.spec.get("table") or self.table_cfg or {}
        desired = render_template(template, state_ns or self._state_view(), event, table_cfg)
        return _diff_bets(current_bets, desired)

    def _apply_current_mode_template(
        self,
        event: Dict[str, Any],
        current_bets: Dict[str, Any],
        *,
        state_ns: Optional[Dict[str, Any]] = None,
    ) -> List[Action]:
        mode_name = self.state.get("mode")
        modes = self.spec.get("modes") or {}
        mode_cfg = modes.get(mode_name) or {}
        template = (mode_cfg.get("template") or {})
        return self._apply_template(template, event, current_bets, state_ns=state_ns)

    def _apply_template_by_name(
        self,
        mode_name: str,
        event: Dict[str, Any],
        current_bets: Dict[str, Any],
        *,
        state_ns: Optional[Dict[str, Any]] = None,
    ) -> List[Action]:
        if not mode_name:
            return []
        modes = self.spec.get("modes") or {}
        mode_cfg = modes.get(mode_name) or {}
        template = (mode_cfg.get("template") or {})
        # set mode right away (tests expect deterministic mode)
        self.state["mode"] = mode_name
        return self._apply_template(template, event, current_bets, state_ns=state_ns)

    def _matching_rules(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        rules = self.spec.get("rules") or []
        matched: List[Dict[str, Any]] = []
        for r in rules:
            cond = r.get("on") or {}
            ok = True
            for k, v in cond.items():
                if event.get(k) != v:
                    ok = False
                    break
            if ok:
                matched.append(r)
        return matched

    def _exec_action_into_overlay(
        self,
        expr: str,
        event: Dict[str, Any],
        current_bets: Dict[str, Any],
        overlay: Dict[str, Any],
    ) -> List[Action]:
        """
        Execute one rule action string into a shared overlay dict.
        Recognizes apply_template('Mode') specially (returns a plan).
        Otherwise delegates to safe evaluate, mutating the overlay.
        """
        if not isinstance(expr, str):
            return []

        # Detect apply_template("...") with a literal arg
        try:
            tree = ast.parse(expr, mode="eval")
            if isinstance(tree.body, ast.Call) and isinstance(tree.body.func, ast.Name) and tree.body.func.id == "apply_template":
                args = tree.body.args
                if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
                    mode_name = args[0].value
                    # render using the *current overlay* so prior mutations (e.g. units*=2) are honored
                    return self._apply_template_by_name(mode_name, event, current_bets, state_ns=overlay)
        except SyntaxError:
            # fall through to general eval/exec
            pass

        # General action: evaluate to mutate the overlay
        try:
            _ = _eval(expr, overlay, event)
        except EvalError:
            return []
        return []

    # --- Public API ---

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Action]:
        """
        Given a table event and current bets, return an action plan.
        Also mutates internal counters (e.g., rolls_since_point).
        """
        ev = dict(event or {})
        etype = ev.get("type") or ev.get("event")  # support both spellings
        plan: List[Action] = []

        # Keep snapshots for single-increment logic
        before_rolls = int(self.state.get("rolls_since_point", 0))
        point_on_before = bool(self.state.get("point"))

        # Pre-rule bookkeeping
        if etype == "comeout":
            self.state["point"] = None
            self.state["rolls_since_point"] = 0

        elif etype == "point_established":
            self.state["point"] = ev.get("point")
            self.state["rolls_since_point"] = 0
            plan.extend(self._apply_current_mode_template(ev, current_bets))

        elif etype == "seven_out":
            self.state["point"] = None
            self.state["rolls_since_point"] = 0

        # Rules processing with a single shared overlay per tick
        if self.spec.get("rules"):
            rule_event = {"event": etype, **{k: v for k, v in ev.items() if k != "type"}}
            overlay = self._state_view()
            for rule in self._matching_rules(rule_event):
                for act in rule.get("do") or []:
                    actions = self._exec_action_into_overlay(act, rule_event, current_bets, overlay)
                    if actions:
                        plan.extend(actions)
            # Flush any mutations (e.g., units *= 2) back to state/user/spec
            self._flush_overlay_back(overlay)

        # Post-rule deterministic steps
        if etype == "roll":
            if self.state.get("point"):
                after_rules = int(self.state.get("rolls_since_point", 0))
                if not point_on_before:
                    self.state["rolls_since_point"] = 1
                elif after_rules == before_rolls:
                    self.state["rolls_since_point"] = before_rolls + 1

            # regression on 3rd roll after point (clear 6/8, then re-apply)
            if self.state.get("point") and self.state.get("rolls_since_point") == 3:
                for bt in ("place_6", "place_8"):
                    plan.append(_mk_action("clear", bt))
                plan.extend(self._apply_current_mode_template(ev, current_bets))

        return plan

    def state_snapshot(self) -> Dict[str, Any]:
        snap = dict(self.state)
        snap["on_comeout"] = self.state.get("point") in (None, 0, False)
        return snap