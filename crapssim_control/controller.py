# ... (header/comments unchanged)

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
    for k, v in ctrl.vars.items():
        ctx[k] = v
    ctx["mode"] = ctrl.mode
    ctx["point"] = ctrl.point or 0
    ctx["on_comeout"] = ctrl.on_comeout
    ctx["rolls_since_point"] = ctrl.rolls_since_point
    for k, v in (table_cfg or {}).items():
        ctx[k] = v
    for k, v in (event or {}).items():
        ctx[k] = v
    # normalize alias so rules can use "event" or "type"
    if "type" in event and "event" not in ctx:
        ctx["event"] = event["type"]
    if "event" in event and "type" not in ctx:
        ctx["type"] = event["event"]
    return ctx


def _render_and_diff(template: Dict[str, Any], ctrl: _CtrlState, event: Dict[str, Any], table_cfg: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict]:
    state = {
        **ctrl.vars,
        "mode": ctrl.mode,
        "point": ctrl.point or 0,
        "on_comeout": ctrl.on_comeout,
        "rolls_since_point": ctrl.rolls_since_point,
        **(table_cfg or {}),
    }
    desired = rt_render_template(template, state, event or {}, table_cfg or {})
    return rt_diff_bets(current_bets or {}, desired)


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

    # --- Legacy adapter hook expected by tests/EngineAdapter ---
    def update_bets(self, _table: Any) -> None:
        """
        Legacy no-op hook. EngineAdapter calls this before each roll. We keep it for compatibility.
        Real bet updates are driven by handle_event() when events arrive.
        """
        return None

    def handle_event(self, event: Dict[str, Any], current_bets: Optional[Dict[str, Dict]] = None) -> List[Dict]:
        self._ingest_event_side_effects(event)

        actions: List[Dict] = []
        for rule in (self.spec.get("rules") or []):
            if not isinstance(rule, dict):
                continue

            on = (rule.get("on") or {})
            # Normalize event with aliases for matching
            ctx_for_on = _mk_ctx(self._ctrl, event, self.table_cfg)

            # 1) event/type key must match if present
            evt_key = on.get("event")
            if evt_key and ctx_for_on.get("type") != evt_key and ctx_for_on.get("event") != evt_key:
                continue

            # 2) all other keys in "on" must match exactly (e.g., bet="pass", result="lose")
            extra_keys = {k: v for k, v in on.items() if k != "event"}
            mismatch = False
            for k, v in extra_keys.items():
                if ctx_for_on.get(k) != v:
                    mismatch = True
                    break
            if mismatch:
                continue

            # Optional condition
            cond_expr = rule.get("if")
            if cond_expr is not None:
                try:
                    if not _boolish(evaluate(str(cond_expr), ctx_for_on, {})):
                        continue
                except EvalError:
                    continue

            # Execute actions
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
        elif et == "shooter_change":
            pass

    def _exec_action(self, act: Any, event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict]:
        if not isinstance(act, str):
            return []

        m = _APPLY_TEMPLATE_RE.match(act)
        if m:
            mode_name = m.group(1)
            template = ((self.spec.get("modes") or {}).get(mode_name) or {}).get("template") or {}
            plan = _render_and_diff(template, self._ctrl, event, self.table_cfg, current_bets)
            return plan

        if _CLEAR_RE.match(act):
            return [{"action": "clear", "bet_type": k} for k in sorted(current_bets.keys())]

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