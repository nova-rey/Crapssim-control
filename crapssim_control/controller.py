# crapssim_control/controller.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from .templates import render_template
from .eval import evaluate as _eval


# Map some engine bet_type names to rules-facing names the tests expect
_ENGINE_TO_RULES_BET = {
    "pass_line": "pass",
    "dont_pass": "dont_pass",
    "field": "field",
}
def _rules_bet_for(bet_type: str) -> str:
    return _ENGINE_TO_RULES_BET.get(bet_type, bet_type)


def _diff_bets_to_actions(
    current: Dict[str, Any],
    desired: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Diff current -> desired into engine actions. Always include both
    'bet_type' (engine) and 'bet' (rules shim), plus 'action' and 'amount'."""
    actions: List[Dict[str, Any]] = []

    def _amt(v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict) and "amount" in v and isinstance(v["amount"], (int, float)):
            return float(v["amount"])
        return None

    curr_amt = {k: _amt(v) for k, v in (current or {}).items()}
    want_amt = {k: _amt(v) for k, v in (desired or {}).items()}

    for bet_type, amount in want_amt.items():
        if amount is None:
            continue
        if curr_amt.get(bet_type) != amount:
            actions.append(
                {"action": "set", "bet_type": bet_type, "bet": _rules_bet_for(bet_type), "amount": amount}
            )

    for bet_type in (curr_amt.keys() - want_amt.keys()):
        actions.append(
            {"action": "remove", "bet_type": bet_type, "bet": _rules_bet_for(bet_type), "amount": 0.0}
        )
    return actions


class _CtrlState:
    def __init__(self, variables: Dict[str, Any], table_cfg: Dict[str, Any]):
        self.vars: Dict[str, Any] = dict(variables or {})
        self.mode: str = (self.vars.get("mode") or "Main")
        self.on_comeout: bool = True
        self.point: Optional[int] = None
        self.table_cfg: Dict[str, Any] = dict(table_cfg or {})
        self.counters: Dict[str, Any] = {
            "seven_outs": 0,
            "points_established": 0,
            "number_frequencies": {n: 0 for n in range(2, 13)},
            "last_event": None,
        }
        self.rolls_since_point: int = 0


def _eval_env(ctrl: _CtrlState, event: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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


def _safe_exec_or_eval(expr: str, env: Dict[str, Any]) -> Any:
    """
    - First try to treat expr as a *statement* (exec) to allow assignments like `x=1`, `x+=1`.
    - If that SyntaxErrors, fall back to expression evaluation via the repo's safe _eval.
    """
    try:
        code = compile(expr, "<ctrl-exec>", "exec")
        exec(code, {}, env)
        return None
    except SyntaxError:
        return _eval(expr, env)


class ControlStrategy:
    """
    Event-driven controller used by tests and the engine adapter.
    """

    def __init__(self, spec: Dict[str, Any], table_cfg: Optional[Dict[str, Any]] = None):
        self._spec = dict(spec or {})
        # allow rules.run_rules_for_event to pass explicit table_cfg
        merged_table = dict(self._spec.get("table") or {})
        if table_cfg:
            merged_table.update(table_cfg)
        self._table_cfg = merged_table
        self._ctrl = _CtrlState(self._spec.get("variables") or {}, self._table_cfg)

    # -------------------------
    # Public adapter hooks
    # -------------------------
    def update_bets(self, table_like: Any) -> None:
        ev_type = "comeout" if self._ctrl.on_comeout else "roll"
        _ = self.handle_event({"type": ev_type, "event": ev_type}, current_bets=_safe_collect_bets(table_like))

    def after_roll(self, table_like: Any, event: Dict[str, Any]) -> None:
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
        event = dict(ev or {})
        event.setdefault("event", event.get("type"))

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
            if self._ctrl.point is not None:
                self._ctrl.rolls_since_point += 1

        rules: List[Dict[str, Any]] = self._spec.get("rules") or []
        plan: List[Dict[str, Any]] = []

        for rule in rules:
            on = rule.get("on") or {}
            if not _matches(on, event):
                continue

            for expr in rule.get("do") or []:
                if isinstance(expr, str) and expr.startswith("apply_template(") and expr.endswith(")"):
                    mode_name = expr[len("apply_template(") : -1].strip().strip("'\"")
                    plan.extend(self._apply_template(mode_name, current_bets or {}, event))
                else:
                    env = _eval_env(self._ctrl, None)
                    _ = _safe_exec_or_eval(expr, env)

                    # reflect mutations
                    for k in list(self._ctrl.vars.keys()):
                        if k in env:
                            self._ctrl.vars[k] = env[k]
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
        tmpl_spec = (self._spec.get("modes") or {}).get(name, {}).get("template") or {}

        variables = self._ctrl.vars
        # accept table configs that use either "level" or "table_level"
        bubble = bool(self._table_cfg.get("bubble"))
        table_level = self._table_cfg.get("level", self._table_cfg.get("table_level"))

        rendered = None
        # prefer the 5-arg form (with point) if available, else 4-arg
        try:
            rendered = render_template(tmpl_spec, variables, bubble, table_level, self._ctrl.point)
        except TypeError:
            rendered = render_template(tmpl_spec, variables, bubble, table_level)

        return _diff_bets_to_actions(current_bets or {}, rendered or {})


def _matches(on: Dict[str, Any], event: Dict[str, Any]) -> bool:
    for k, v in (on or {}).items():
        if event.get(k) != v:
            return False
    return True


def _safe_collect_bets(table_like: Any) -> Dict[str, Any]:
    if hasattr(table_like, "get_player_bets"):
        try:
            bets = table_like.get_player_bets()
            if isinstance(bets, dict):
                return bets
        except Exception:
            pass

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