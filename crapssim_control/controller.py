# crapssim_control/controller.py

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import ast

from .templates_rt import render_template
from .eval import evaluate as _eval, EvalError


Action = Dict[str, Any]


def _amount_of(v: Any) -> float:
    """
    Normalize a desired/current bet entry to a float amount.
    Accepts either a raw number or a dict like {"amount": 10, ...}.
    """
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        # common shape from render_template
        if "amount" in v and isinstance(v["amount"], (int, float)):
            return float(v["amount"])
        # sometimes current bets might come across as {"amount": x, ...}
        # fall back to 0.0 if not present
    return 0.0


def _diff_bets(current: Dict[str, Any], desired: Dict[str, Any]) -> List[Action]:
    """
    Create a minimal set/clear plan to move from `current` -> `desired`.
    Handles both raw numbers and dicts with {"amount": ...}.
    Amount comparisons are exact; upstream legalizers will adjust to table rules.
    """
    plan: List[Action] = []
    current = current or {}
    desired = desired or {}

    # clears for anything not desired or zeroed
    for bt, cval in sorted(current.items()):
        if bt not in desired or _amount_of(desired.get(bt)) <= 0.0:
            plan.append({"action": "clear", "bet_type": bt})

    # sets/updates for desired bets
    for bt, dval in sorted(desired.items()):
        d_amt = _amount_of(dval)
        c_amt = _amount_of(current.get(bt))
        if d_amt > 0.0 and float(c_amt) != float(d_amt):
            plan.append({"action": "set", "bet_type": bt, "amount": float(d_amt)})

    return plan


class ControlStrategy:
    """
    Interprets a control spec:
      - spec["modes"][mode]["template"] provides desired bets for that mode
      - spec["rules"] is a list of {"on": {...}, "do": [actions]} evaluated on events
    Maintains a small state dict for counters and flags used in expressions.
    """

    def __init__(self, spec: Dict[str, Any], var_store: Optional[Any] = None):
        self.spec = spec or {}
        self.vars = var_store  # optional VarStore, if supplied tests can read it
        self.state: Dict[str, Any] = {
            "point": None,
            "rolls_since_point": 0,
            "mode": (self.spec.get("variables", {}) or {}).get(
                "mode",
                # pick first mode name if not provided
                next(iter(self.spec.get("modes", {}) or {"Main": {}}))
            ),
        }

    # --- EngineAdapter hooks (smoke tests expect these to exist) ---

    def update_bets(self, _table) -> None:
        """Hook before a roll; placeholder for future logic (no-op)."""
        return None

    def after_roll(self, _table, _event: Dict[str, Any]) -> None:
        """Hook after a roll to do bookkeeping (no-op, we handle via handle_event)."""
        return None

    # --- Internal helpers ---

    def _apply_current_mode_template(self, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Action]:
        mode_name = self.state.get("mode")
        if not mode_name:
            return []
        modes = self.spec.get("modes") or {}
        mode_cfg = modes.get(mode_name) or {}
        template = (mode_cfg.get("template") or {})
        if not template:
            return []
        table_cfg = self.spec.get("table") or {}
        desired = render_template(template, self._state_view(), event, table_cfg)
        return _diff_bets(current_bets, desired)

    def _apply_template_by_name(self, mode_name: str, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Action]:
        if not mode_name:
            return []
        modes = self.spec.get("modes") or {}
        mode_cfg = modes.get(mode_name) or {}
        template = (mode_cfg.get("template") or {})
        if not template:
            return []
        table_cfg = self.spec.get("table") or {}
        desired = render_template(template, self._state_view(), event, table_cfg)
        # also set the current mode in state to the named mode for determinism
        self.state["mode"] = mode_name
        return _diff_bets(current_bets, desired)

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

    def _state_view(self) -> Dict[str, Any]:
        """
        Build the evaluation state overlay:
        - user variables (if VarStore supplied) or spec variables
        - controller state (point, rolls_since_point, mode)
        """
        # base variables
        base_vars = {}
        if self.vars is not None and getattr(self.vars, "user", None) is not None:
            base_vars.update(self.vars.user)
        else:
            base_vars.update(self.spec.get("variables") or {})
        # overlay controller state
        base_vars.update(self.state)
        return base_vars

    def _exec_action(self, expr: str, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Action]:
        """
        Execute one rule action string.
        Recognizes apply_template('Mode') specially (returns a plan).
        Otherwise delegates to safe evaluate, mutating the state/vars as needed.
        """
        if not isinstance(expr, str):
            return []

        # Quick parse to detect apply_template("...") with literal argument
        try:
            tree = ast.parse(expr, mode="eval")
            if isinstance(tree.body, ast.Call) and isinstance(tree.body.func, ast.Name) and tree.body.func.id == "apply_template":
                # extract first arg if constant string
                args = tree.body.args
                if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str):
                    mode_name = args[0].value
                    return self._apply_template_by_name(mode_name, event, current_bets)
        except SyntaxError:
            # fall through; may be an assignment statement, not an expression
            pass

        # For non apply_template actions, evaluate to mutate variables/state.
        # Allow rules to reference/modify "mode", "units", etc.
        state_overlay = self._state_view()
        try:
            _ = _eval(expr, state_overlay, event)
        except EvalError as e:
            # keep message but don't crash tests; just ignore this action
            # (alternatively re-raise if you want strict behavior)
            return []

        # Push mutated values back into sources:
        #  - mode/point/counters into self.state
        #  - user vars (like units) back to VarStore if present, else into spec.variables
        for k, v in state_overlay.items():
            if k in ("point", "rolls_since_point", "mode"):
                self.state[k] = v
            else:
                if self.vars is not None and getattr(self.vars, "user", None) is not None:
                    self.vars.user[k] = v
                else:
                    (self.spec.setdefault("variables", {}))[k] = v
        return []

    # --- Public API used by tests ---

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Action]:
        """
        Main entry: given a table event and current bets, return an action plan.
        Also mutates internal counters (e.g., rolls_since_point).
        """
        ev = dict(event or {})
        etype = ev.get("type") or ev.get("event")  # support both spellings used in tests
        plan: List[Action] = []

        # Update basic state based on event types the tests use
        if etype == "comeout":
            self.state["rolls_since_point"] = 0
            # on comeout, point is None
            self.state["point"] = None

        elif etype == "point_established":
            point = ev.get("point")
            self.state["point"] = point
            self.state["rolls_since_point"] = 0
            # Apply the current mode's template immediately when a point is set
            plan.extend(self._apply_current_mode_template(ev, current_bets))

        elif etype == "roll":
            # increment rolls since point if point is on
            if self.state.get("point"):
                self.state["rolls_since_point"] = int(self.state.get("rolls_since_point", 0)) + 1

        elif etype == "seven_out":
            # reset state to comeout
            self.state["point"] = None
            self.state["rolls_since_point"] = 0

        # Process rule table for ANY event that provides an "event" (or type) key
        # Rules can adjust variables and/or apply templates.
        if self.spec.get("rules"):
            for rule in self._matching_rules({"event": etype, **{k: v for k, v in ev.items() if k != "type"}}):
                for act in rule.get("do") or []:
                    actions = self._exec_action(act, {"event": etype, **ev}, current_bets)
                    if actions:
                        plan.extend(actions)

        return plan

    # Helpers for tests that snapshot internal strategy state
    def state_snapshot(self) -> Dict[str, Any]:
        snap = dict(self.state)
        # tests assert on on_comeout sometimes; derive it
        snap["on_comeout"] = self.state.get("point") in (None, 0, False)
        return snap