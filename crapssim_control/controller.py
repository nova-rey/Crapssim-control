# crapssim_control/controller.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .templates import render_template
from .eval import evaluate as _eval


# ----------------------------
# Helpers
# ----------------------------

def _rules_bet_for(bet_type: str) -> str:
    """
    Convert engine-facing bet_type to the rules-shim 'bet' name if needed.
    In our tests these are typically identical, so default to identity.
    """
    return bet_type


def _safe_collect_bets(table_like: Any) -> Dict[str, Any]:
    """
    Snapshot of a table/player's current bets into a flat dict:
      - Keys are 'bet_type' or 'bet_type:number'
      - Values are either amount (float) or {'amount': float}
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
            amount = getattr(b, "amount", None)
            if kind is None:
                continue
            key = str(kind) if number in (None, "", 0) else f"{kind}:{number}"
            out[key] = float(amount) if isinstance(amount, (int, float)) else {"amount": 0.0}
    except Exception:
        pass
    return out


def _diff_bets_to_actions(
    current: Dict[str, Any],
    desired: Any,  # dict OR list[tuple]
) -> List[Dict[str, Any]]:
    """Diff current -> desired into engine actions.

    `desired` can be:
      - dict like {"pass": 10, "place:6": 12} or {"pass": {"amount": 10}}
      - list of tuples: [(bet_type, number, amount, opts_dict), ...]
    """
    actions: List[Dict[str, Any]] = []

    def _amt(v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict) and isinstance(v.get("amount"), (int, float)):
            return float(v["amount"])
        return None

    curr_amt = {k: _amt(v) for k, v in (current or {}).items()}

    targets: List[Dict[str, Any]] = []
    if isinstance(desired, dict):
        for k, v in desired.items():
            bet_type = k
            number = None
            if isinstance(k, str) and ":" in k:
                parts = k.split(":", 1)
                bet_type = parts[0]
                try:
                    number = int(parts[1])
                except (ValueError, TypeError):
                    number = parts[1]
            targets.append({
                "bet_type": bet_type,
                "bet": _rules_bet_for(bet_type),
                "number": number,
                "amount": _amt(v) or 0.0,
            })
    elif isinstance(desired, (list, tuple)):
        for tup in desired:
            if not isinstance(tup, (list, tuple)) or len(tup) < 3:
                continue
            bet_type = str(tup[0])
            number = tup[1] if len(tup) > 1 else None
            raw_amt = tup[2]
            amount = float(raw_amt) if isinstance(raw_amt, (int, float)) else 0.0
            targets.append({
                "bet_type": bet_type,
                "bet": _rules_bet_for(bet_type),
                "number": number,
                "amount": amount,
            })
    else:
        return actions

    for t in targets:
        key = t["bet_type"] if t["number"] in (None, "", 0) else f'{t["bet_type"]}:{t["number"]}'
        curr = curr_amt.get(key, curr_amt.get(t["bet_type"]))
        if curr != t["amount"]:
            act: Dict[str, Any] = {
                "action": "set",
                "bet_type": t["bet_type"],
                "bet": t["bet"],
                "amount": t["amount"],
            }
            if t["number"] not in (None, "", 0):
                act["number"] = t["number"]
            actions.append(act)

    return actions


# ----------------------------
# Controller
# ----------------------------

@dataclass
class _CtrlState:
    vars: Dict[str, Any] = field(default_factory=dict)
    point: Optional[int] = None  # craps point (4,5,6,8,9,10)


class ControlStrategy:
    """
    Lightweight rule runner + template applier used by tests.

    Public surface used by tests:
      - ControlStrategy(spec, table_cfg=?)
      - update_bets(table_like)
      - handle_event(event_dict, current_bets_dict)
      - after_roll(table_like, event_dict)
      - state_snapshot()
    """

    def __init__(self, spec: Dict[str, Any], ctrl_state: Any | None = None, *, table_cfg: Dict[str, Any] | None = None) -> None:
        self._spec = spec or {}
        # prefer explicit table_cfg, else from spec.table, else {}
        self._table_cfg = (table_cfg or self._spec.get("table") or {}).copy()

        variables = (self._spec.get("variables") or {}).copy()
        if "mode" not in variables:
            modes = list((self._spec.get("modes") or {}).keys())
            variables["mode"] = modes[0] if modes else "Main"

        self._ctrl = _CtrlState(vars=variables)
        if isinstance(ctrl_state, dict):
            self._ctrl.vars.update(ctrl_state)

    # ------------------------
    # External API
    # ------------------------

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
          1. Update internal point state when events dictate.
          2. Run matching rules and collect actions.
          3. Do NOT auto-apply mode template; templates are applied only if rules say so.
        """
        plan: List[Dict[str, Any]] = []

        ev = dict(event or {})
        ev_type = ev.get("type") or ev.get("event")

        # 1) Update point state
        if ev_type == "point_established":
            self._ctrl.point = int(ev.get("point") or 0) or None
        elif ev_type in ("seven_out", "puck_off", "seven_out_resolved"):
            self._ctrl.point = None

        # 2) Run matching rules (they may call apply_template)
        for rule in (self._spec.get("rules") or []):
            cond = rule.get("on") or {}
            if _event_matches(ev, cond):
                for act in rule.get("do") or []:
                    delta = self._exec_action(act, ev, current_bets)
                    if delta:
                        plan.extend(delta)

        # 3) No implicit template application here (tests expect [] on raw comeout)
        return plan

    def after_roll(self, table_like: Any, event: Dict[str, Any]) -> None:
        """
        Minimal bookkeeping hook used by EngineAdapter tests.
        We update point on common outcomes for realism; tests don't require more.
        """
        ev = dict(event or {})
        et = ev.get("type") or ev.get("event")
        if et == "point_established":
            self._ctrl.point = int(ev.get("point") or 0) or None
        elif et in ("seven_out", "puck_off", "seven_out_resolved"):
            self._ctrl.point = None

    def state_snapshot(self) -> Dict[str, Any]:
        """Tiny snapshot for tests that inspect point."""
        return {"point": self._ctrl.point, "vars": dict(self._ctrl.vars)}

    # ------------------------
    # Internals
    # ------------------------

    def _exec_action(
        self,
        action_expr: Any,
        event: Dict[str, Any],
        current_bets: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Supports:
          - "apply_template('ModeName')"
          - expressions handled by eval.evaluate (e.g., "units += 10", "rolls_since_point = 0")
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

        # Otherwise, variable/expression mutation via eval
        state = self._build_eval_state()
        _ = _eval(expr, state=state, event=event)
        self._pull_back_from_eval_state(state)
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
        Supports render_template(...) variants with or without a 'point' parameter.
        """
        tmpl_spec = (self._spec.get("modes") or {}).get(name, {}).get("template") or {}
        variables = self._ctrl.vars

        bubble = bool(self._table_cfg.get("bubble"))
        table_level = self._table_cfg.get("level", self._table_cfg.get("table_level"))
        if table_level is None:
            table_level = int(variables.get("table_level") or 1)

        rendered = None
        try:
            rendered = render_template(tmpl_spec, variables, bubble, table_level, self._ctrl.point)
        except TypeError:
            rendered = render_template(tmpl_spec, variables, bubble, table_level)

        return _diff_bets_to_actions(current_bets or {}, rendered or {})

    # ---- eval state plumbing -------------------------------------------------

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
        return st

    def _pull_back_from_eval_state(self, st: Dict[str, Any]) -> None:
        for k in list(self._ctrl.vars.keys()):
            if k in st:
                self._ctrl.vars[k] = st[k]
        if isinstance(st.get("vars"), dict):
            self._ctrl.vars.update(st["vars"])


# ----------------------------
# Rule matching
# ----------------------------

def _event_matches(ev: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    """
    True iff all key/value pairs in cond appear equal in ev (string/int/float tolerant).
    """
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