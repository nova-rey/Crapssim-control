# crapssim_control/controller.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .templates import render_template
from .eval import evaluate as _eval


def _engine_bet_type_for(bet_name: str) -> str:
    """Map rules bet name -> engine bet_type."""
    mapping = {
        "pass": "pass_line",
        "dont_pass": "dont_pass",
        # add more mappings here if needed; default is identity
    }
    return mapping.get(bet_name, bet_name)


def _safe_collect_bets(table_like: Any) -> Dict[str, Any]:
    """
    Snapshot of current bets into a dict like:
      {'pass': 10.0, 'place:6': 12.0, ...}
    This is only used to diff against desired template output.
    """
    out: Dict[str, Any] = {}
    try:
        bets = getattr(table_like, "bets", None)
        if bets is None and hasattr(table_like, "player"):
            bets = getattr(table_like.player, "bets", None)
        if not bets:
            return out
        for b in bets:
            kind = getattr(b, "kind", None) or getattr(b, "bet_type", None) or getattr(b, "bet", None)
            number = getattr(b, "number", None)
            amount = getattr(b, "amount", 0.0)
            key = str(kind) if number in (None, "", 0) else f"{kind}:{number}"
            out[key] = float(amount) if isinstance(amount, (int, float)) else 0.0
    except Exception:
        pass
    return out


def _diff_bets_to_actions(current: Dict[str, Any], desired: Any) -> List[Dict[str, Any]]:
    """
    Convert desired bets into engine actions, comparing to current.
    desired can be:
      - dict: {"pass": 10, "place:6": 12}
      - list[tuple]: [("pass", None, 10, {}), ("place", 6, 12, {})]
    We always return actions that include BOTH:
      - 'bet'      (rules name, e.g. 'pass')
      - 'bet_type' (engine name, e.g. 'pass_line')
    """
    def _amt(v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict) and isinstance(v.get("amount"), (int, float)):
            return float(v["amount"])
        return None

    want: List[Tuple[str, Optional[int], float]] = []
    if isinstance(desired, dict):
        for k, v in desired.items():
            bet_name = k
            number: Optional[int] = None
            if isinstance(k, str) and ":" in k:
                bet_name, num_str = k.split(":", 1)
                try:
                    number = int(num_str)
                except (ValueError, TypeError):
                    number = None
            a = _amt(v)
            if a is not None:
                want.append((bet_name, number, a))
    elif isinstance(desired, (list, tuple)):
        for tup in desired:
            if not isinstance(tup, (list, tuple)) or len(tup) < 3:
                continue
            bet_name = str(tup[0])
            number = tup[1] if len(tup) > 1 else None
            raw_amt = tup[2]
            if isinstance(raw_amt, (int, float)):
                want.append((bet_name, number, float(raw_amt)))

    actions: List[Dict[str, Any]] = []
    curr_amt = dict(current or {})
    for bet_name, number, amount in want:
        key = bet_name if number in (None, "", 0) else f"{bet_name}:{number}"
        if curr_amt.get(key) != amount:
            act: Dict[str, Any] = {
                "action": "set",
                "bet": bet_name,                               # rules name (used by tests in rules.py)
                "bet_type": _engine_bet_type_for(bet_name),   # engine-facing
                "amount": amount,
            }
            if number not in (None, "", 0):
                act["number"] = number
            actions.append(act)
    return actions


@dataclass
class _CtrlState:
    vars: Dict[str, Any] = field(default_factory=dict)
    point: Optional[int] = None
    rolls_since_point: int = 0


class ControlStrategy:
    """
    Public API used by tests:
      - ControlStrategy(spec, table_cfg=?)
      - update_bets(table_like)
      - handle_event(event_dict, current_bets_dict)
      - after_roll(table_like, event_dict)
      - state_snapshot()
    """

    def __init__(
        self,
        spec: Dict[str, Any],
        ctrl_state: Any | None = None,
        *,
        table_cfg: Dict[str, Any] | None = None,
    ) -> None:
        self._spec = spec or {}
        self._table_cfg = (table_cfg or self._spec.get("table") or {}).copy()

        variables = (self._spec.get("variables") or {}).copy()
        if "mode" not in variables:
            modes = list((self._spec.get("modes") or {}).keys())
            variables["mode"] = modes[0] if modes else "Main"

        self._ctrl = _CtrlState(vars=variables)
        if isinstance(ctrl_state, dict):
            self._ctrl.vars.update(ctrl_state)

    # ---------------- External surface ----------------

    def update_bets(self, table_like: Any) -> List[Dict[str, Any]]:
        """
        Called by EngineAdapter between rolls. We synthesize a coarse event so
        the same state machine applies.
        """
        ev_type = "comeout" if self._ctrl.point in (None, 0, "") else "point_on"
        current = _safe_collect_bets(table_like)
        return self.handle_event({"type": ev_type, "event": ev_type}, current_bets=current)

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Steps:
          1) Update point bookkeeping.
          2) Auto-apply current mode template on point_established (per tests).
          3) Evaluate matching rules.
        """
        plan: List[Dict[str, Any]] = []
        ev = dict(event or {})
        etype = ev.get("type") or ev.get("event")
        mode_name = str(self._ctrl.vars.get("mode", "Main"))

        # 1) Point & roll counters
        if etype == "point_established":
            self._ctrl.point = int(ev.get("point") or 0) or None
            self._ctrl.rolls_since_point = 0
        elif etype in ("seven_out", "puck_off", "seven_out_resolved"):
            self._ctrl.point = None
            self._ctrl.rolls_since_point = 0
        elif etype == "roll" and self._ctrl.point:
            self._ctrl.rolls_since_point += 1

        # 2) Auto-apply template on point_established so Aggressive/Main fires immediately
        if etype == "point_established":
            plan.extend(self._apply_template(mode_name, current_bets or {}, ev))

        # 3) Run matching rules (they can also call apply_template)
        for rule in (self._spec.get("rules") or []):
            cond = rule.get("on") or {}
            if _event_matches(ev, cond):
                for act in rule.get("do") or []:
                    delta = self._exec_action(act, ev, current_bets)
                    if delta:
                        plan.extend(delta)

        return plan

    def after_roll(self, table_like: Any, event: Dict[str, Any]) -> None:
        """Minimal hook used by EngineAdapter tests."""
        ev = dict(event or {})
        et = ev.get("type") or ev.get("event")
        if et == "point_established":
            self._ctrl.point = int(ev.get("point") or 0) or None
            self._ctrl.rolls_since_point = 0
        elif et in ("seven_out", "puck_off", "seven_out_resolved"):
            self._ctrl.point = None
            self._ctrl.rolls_since_point = 0
        elif et == "roll" and self._ctrl.point:
            self._ctrl.rolls_since_point += 1

    def state_snapshot(self) -> Dict[str, Any]:
        """Small snapshot used by tests."""
        return {
            "point": self._ctrl.point,
            "rolls_since_point": self._ctrl.rolls_since_point,
            "vars": dict(self._ctrl.vars),
        }

    # ---------------- Internals ----------------

    def _exec_action(self, action_expr: Any, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Supports:
          - "apply_template('ModeName')"
          - expression mutations handled by eval.evaluate (e.g., "units += 10", "x = 0")
        """
        if not isinstance(action_expr, str):
            return []
        expr = action_expr.strip()

        # apply_template('Mode')
        if expr.startswith("apply_template(") and expr.endswith(")"):
            inside = expr[len("apply_template("):-1].strip()
            if (inside.startswith("'") and inside.endswith("'")) or (inside.startswith('"') and inside.endswith('"')):
                inside = inside[1:-1]
            return self._apply_template(inside, current_bets or {}, event)

        # Otherwise, delegate to expression evaluator
        state = self._build_eval_state()
        _ = _eval(expr, state=state, event=event)
        self._pull_back_from_eval_state(state)
        return []

    def _apply_template(self, name: str, current_bets: Dict[str, Dict], event: Dict[str, Any]) -> List[Dict[str, Any]]:
        tmpl_spec = (self._spec.get("modes") or {}).get(name, {}).get("template") or {}
        variables = self._ctrl.vars

        bubble = bool(self._table_cfg.get("bubble"))
        table_level = self._table_cfg.get("level", self._table_cfg.get("table_level"))
        if table_level is None:
            table_level = int(variables.get("table_level") or 1)

        try:
            rendered = render_template(tmpl_spec, variables, bubble, table_level, self._ctrl.point)
        except TypeError:
            rendered = render_template(tmpl_spec, variables, bubble, table_level)

        return _diff_bets_to_actions(current_bets or {}, rendered or {})

    # ---- eval state plumbing

    def _build_eval_state(self) -> Dict[str, Any]:
        st: Dict[str, Any] = {}
        st.update(self._ctrl.vars)
        st["vars"] = self._ctrl.vars
        st.setdefault("counters", {
            "points_established": 0,
            "points_made": 0,
            "seven_outs": 0,
            "last_event": None,
            "number_frequencies": {i: 0 for i in range(2, 13)},
        })
        st["event"] = None
        st["on_comeout"] = self._ctrl.point in (None, 0, "")
        st["point"] = self._ctrl.point
        st["rolls_since_point"] = self._ctrl.rolls_since_point
        return st

    def _pull_back_from_eval_state(self, st: Dict[str, Any]) -> None:
        for k in list(self._ctrl.vars.keys()):
            if k in st:
                self._ctrl.vars[k] = st[k]
        if isinstance(st.get("vars"), dict):
            self._ctrl.vars.update(st["vars"])


def _event_matches(ev: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    if not cond:
        return True
    for k, want in cond.items():
        if k not in ev:
            return False
        have = ev[k]
        if isinstance(want, (int, float)) and isinstance(have, str):
            try:
                have = float(have) if "." in have else int(have)
            except Exception:
                pass
        if have != want:
            return False
    return True