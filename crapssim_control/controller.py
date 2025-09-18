from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import re

from .eval import eval_bool, eval_num, evaluate, EvalError
from .templates_rt import render_template as rt_render_template, diff_bets as rt_diff_bets


@dataclass
class _CtrlState:
    vars: Dict[str, Any] = field(default_factory=dict)
    mode: Optional[str] = None
    point: int | None = None
    on_comeout: bool = True
    rolls_since_point: int = 0
    logs: List[str] = field(default_factory=list)


_ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")
_INPLACE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*([+|-])=\s*(.+?)\s*$")
_APPLY_TEMPLATE_RE = re.compile(r"^\s*apply_template\(\s*'([^']+)'\s*\)\s*$")
_LOG_RE = re.compile(r'^\s*log\(\s*"([^"]*)"\s*\)\s*$')
_CLEAR_RE = re.compile(r"^\s*clear_bets\(\s*\)\s*$")


def _boolish(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("true", "t", "1", "yes", "y", "on"):
            return True
        if s in ("false", "f", "0", "no", "n", "off"):
            return False
    return False


def _mk_ctx(ctrl: _CtrlState, event: Dict[str, Any], table_cfg: Dict[str, Any]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}
    ctx.update(ctrl.vars)
    ctx["mode"] = ctrl.mode
    ctx["point"] = ctrl.point or 0
    ctx["on_comeout"] = ctrl.on_comeout
    ctx["rolls_since_point"] = ctrl.rolls_since_point
    ctx.update(table_cfg or {})
    ctx.update(event or {})
    if "type" in event and "event" not in ctx:
        ctx["event"] = event["type"]
    if "event" in event and "type" not in ctx:
        ctx["type"] = event["event"]
    return ctx


def _bet_type_to_kind_number(bet_type: str) -> Tuple[Optional[str], Optional[int]]:
    if bet_type == "pass_line":
        return ("pass", None)
    if bet_type == "dont_pass":
        return ("dont_pass", None)
    if bet_type == "field":
        return ("field", None)
    if bet_type.startswith("place_"):
        try:
            return ("place", int(bet_type.split("_", 1)[1]))
        except Exception:
            return ("place", None)
    if bet_type.startswith("lay_"):
        try:
            return ("lay", int(bet_type.split("_", 1)[1]))
        except Exception:
            return ("lay", None)
    if bet_type.startswith("odds_"):
        try:
            return ("odds", int(bet_type.split("_", 1)[1]))
        except Exception:
            return ("odds", None)
    return (None, None)


def _enhance_actions_with_kind_number_and_clear(policy_current: Dict[str, Dict], actions: List[Dict]) -> List[Dict]:
    """
    Post-process diff actions to:
      1) enforce deterministic 'clear-then-set' for ANY existing bet we change (even if amount
         is the same after legalization, stay deterministic for tests)
      2) attach 'kind' and 'number' keys for tests that read them
    """
    out: List[Dict] = []
    for a in actions:
        if a.get("action") == "set":
            bt = a["bet_type"]
            # If a bet exists in current policy, emit a 'clear' first (deterministic)
            if bt in (policy_current or {}):
                k, n = _bet_type_to_kind_number(bt)
                out.append({"action": "clear", "bet_type": bt, "kind": k, "number": n})
            # Always attach kind/number to the set
            k, n = _bet_type_to_kind_number(bt)
            a = dict(a)
            a["kind"], a["number"] = k, n
            out.append(a)
        elif a.get("action") == "clear":
            bt = a["bet_type"]
            k, n = _bet_type_to_kind_number(bt)
            a = dict(a)
            a["kind"], a["number"] = k, n
            out.append(a)
        else:
            out.append(a)
    return out


def _render_and_diff(template: Dict[str, Any], ctrl: _CtrlState, event: Dict[str, Any],
                     table_cfg: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict]:
    state = {
        **ctrl.vars,
        "mode": ctrl.mode,
        "point": ctrl.point or 0,
        "on_comeout": ctrl.on_comeout,
        "rolls_since_point": ctrl.rolls_since_point,
        **(table_cfg or {}),
    }
    desired = rt_render_template(template, state, event or {}, table_cfg or {})
    base = rt_diff_bets(current_bets or {}, desired)
    return _enhance_actions_with_kind_number_and_clear(current_bets or {}, base)


class ControlStrategy:
    def __init__(self, spec: Dict[str, Any], table_cfg: Optional[Dict[str, Any]] = None) -> None:
        self.spec = dict(spec or {})
        self.table_cfg = dict(table_cfg or spec.get("table") or {})
        self._ctrl = _CtrlState(
            vars=dict((self.spec.get("variables") or {})),
            mode=(self.spec.get("variables") or {}).get("mode"),
            on_comeout=True,
            point=None,
            rolls_since_point=0,
        )

    # --- Legacy adapter hooks expected by tests/EngineAdapter ---
    def update_bets(self, _table: Any) -> None:
        return None

    def after_roll(self, _table: Any, event: Dict[str, Any]) -> None:
        self._ingest_event_side_effects(event)

    # --- Core event handler ---
    def handle_event(self, event: Dict[str, Any], current_bets: Optional[Dict[str, Dict]] = None) -> List[Dict]:
        self._ingest_event_side_effects(event)

        actions: List[Dict] = []
        for rule in (self.spec.get("rules") or []):
            if not isinstance(rule, dict):
                continue

            on = (rule.get("on") or {})
            ctx_for_on = _mk_ctx(self._ctrl, event, self.table_cfg)

            evt_key = on.get("event")
            if evt_key and ctx_for_on.get("type") != evt_key and ctx_for_on.get("event") != evt_key:
                continue

            extra_keys = {k: v for k, v in on.items() if k != "event"}
            if any(ctx_for_on.get(k) != v for k, v in extra_keys.items()):
                continue

            cond_expr = rule.get("if")
            if cond_expr is not None:
                try:
                    if not _boolish(evaluate(str(cond_expr), ctx_for_on, {})):
                        continue
                except EvalError:
                    continue

            for act in (rule.get("do") or []):
                plan_delta = self._exec_action(act, event, current_bets or {})
                if plan_delta:
                    actions.extend(plan_delta)

        return actions

    def state_snapshot(self) -> Dict[str, Any]:
        return {
            "vars": dict(self._ctrl.vars),
            "mode": self._ctrl.mode,
            "point": self._ctrl.point,
            "on_comeout": self._ctrl.on_comeout,
            "rolls_since_point": self._ctrl.rolls_since_point,
            "logs": list(self._ctrl.logs),
            "table_cfg": dict(self.table_cfg),
        }

    def _ingest_event_side_effects(self, event: Dict[str, Any]) -> None:
        et = event.get("type") or event.get("event")
        if et == "comeout":
            self._ctrl.on_comeout = True
            self._ctrl.point = None
            self._ctrl.rolls_since_point = 0
        elif et == "point_established":
            p = event.get("point")
            try:
                self._ctrl.point = int(p) if p is not None else None
            except Exception:
                self._ctrl.point = None
            self._ctrl.on_comeout = False
            self._ctrl.rolls_since_point = 0
        elif et == "roll":
            if not self._ctrl.on_comeout and self._ctrl.point:
                self._ctrl.rolls_since_point += 1
        elif et == "seven_out":
            self._ctrl.on_comeout = True
            self._ctrl.point = None
            self._ctrl.rolls_since_point = 0

    def _exec_action(self, act: Any, event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict]:
        if not isinstance(act, str):
            return []

        m = _APPLY_TEMPLATE_RE.match(act)
        if m:
            mode_name = m.group(1)
            template = ((self.spec.get("modes") or {}).get(mode_name) or {}).get("template") or {}
            return _render_and_diff(template, self._ctrl, event, self.table_cfg, current_bets)

        if _CLEAR_RE.match(act):
            plan = []
            for bet_type in sorted(current_bets.keys()):
                k, n = _bet_type_to_kind_number(bet_type)
                plan.append({"action": "clear", "bet_type": bet_type, "kind": k, "number": n})
            return plan

        m = _LOG_RE.match(act)
        if m:
            self._ctrl.logs.append(m.group(1))
            return []

        m = _INPLACE_RE.match(act)
        if m:
            name, op, expr = m.group(1), m.group(2), m.group(3)
            ctx = _mk_ctx(self._ctrl, event, self.table_cfg)
            try:
                delta = eval_num(expr, ctx, {})
            except EvalError:
                return []
            cur = self._ctrl.vars.get(name, 0)
            try:
                curf = float(cur)
            except Exception:
                curf = 0.0
            newv = (curf + delta) if op == "+" else (curf - delta)
            self._ctrl.vars[name] = int(newv) if float(newv).is_integer() else newv
            return []

        m = _ASSIGN_RE.match(act)
        if m:
            name, expr = m.group(1), m.group(2)
            ctx = _mk_ctx(self._ctrl, event, self.table_cfg)
            try:
                val = evaluate(expr, ctx, {})
            except EvalError:
                return []
            if name == "mode":
                self._ctrl.mode = str(val)
            else:
                if isinstance(val, (int, float)) and float(val).is_integer():
                    val = int(val)
                self._ctrl.vars[name] = val
            return []

        return []