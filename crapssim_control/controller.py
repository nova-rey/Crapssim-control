"""
controller.py -- Batch 15: ControlStrategy core runtime

Turns events into actions by:
  events_std.EventStream  → rules (SPEC) → template rendering (templates_rt) → diff → action plan

Design goals:
  - Deterministic & idempotent action plans (clears first alpha, sets alpha)
  - Minimal control state: vars + mode + point/comeout flags + rolls_since_point
  - Back-compat: still importable as `from crapssim_control import ControlStrategy`

Public surface:
  ControlStrategy(spec: dict, table_cfg: dict | None = None)
    .handle_event(event: dict, current_bets: dict | None = None) -> list[dict]
    .state_snapshot() -> dict
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import re

from .eval import eval_bool, eval_num, evaluate, EvalError
from .templates_rt import render_template as rt_render_template, diff_bets as rt_diff_bets


# -----------------------------
# Small control state
# -----------------------------

@dataclass
class _CtrlState:
    vars: Dict[str, Any] = field(default_factory=dict)
    mode: Optional[str] = None
    # table-ish flags used by rules/templates context
    point: int | None = None
    on_comeout: bool = True
    rolls_since_point: int = 0
    # logs
    logs: List[str] = field(default_factory=list)


# -----------------------------
# Helpers
# -----------------------------

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
    # vars first (strategy variables)
    for k, v in ctrl.vars.items():
        ctx[k] = v
    # control flags
    ctx["mode"] = ctrl.mode
    ctx["point"] = ctrl.point or 0
    ctx["on_comeout"] = ctrl.on_comeout
    ctx["rolls_since_point"] = ctrl.rolls_since_point
    # table cfg (bubble, level, etc.)
    for k, v in (table_cfg or {}).items():
        ctx[k] = v
    # event fields (roll, seven_out, etc.)
    for k, v in (event or {}).items():
        ctx[k] = v
    return ctx


def _render_and_diff(template: Dict[str, Any], ctrl: _CtrlState, event: Dict[str, Any], table_cfg: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict]:
    # Build state/event context for template evaluation
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


# -----------------------------
# Controller
# -----------------------------

class ControlStrategy:
    """
    Core runtime: feeds SPEC rules with events and returns a reconciled action plan.
    """
    def __init__(self, spec: Dict[str, Any], table_cfg: Optional[Dict[str, Any]] = None) -> None:
        self.spec = dict(spec or {})
        self.table_cfg = dict(table_cfg or spec.get("table") or {})
        # initialize control vars from spec.variables (copy)
        self._ctrl = _CtrlState(
            vars=dict((self.spec.get("variables") or {})),
            mode=(self.spec.get("variables") or {}).get("mode"),
            on_comeout=True,
            point=None,
            rolls_since_point=0,
        )

    # --- public API ---

    def handle_event(self, event: Dict[str, Any], current_bets: Optional[Dict[str, Dict]] = None) -> List[Dict]:
        """
        Process a single standardized event and return an idempotent action plan.
        """
        # 1) update table-ish flags first (for rules that depend on them)
        self._ingest_event_side_effects(event)

        # 2) run rules (ordered)
        actions: List[Dict] = []
        for rule in (self.spec.get("rules") or []):
            if not isinstance(rule, dict):
                continue
            on = (rule.get("on") or {}).get("event")
            if on and on != event.get("type"):
                continue  # not for this event

            # Build eval context
            ctx = _mk_ctx(self._ctrl, event, self.table_cfg)

            # Optional condition
            cond_expr = rule.get("if")
            if cond_expr is not None:
                try:
                    if not _boolish(evaluate(str(cond_expr), ctx, {})):
                        continue  # condition failed
                except EvalError:
                    # conservative: skip rule on eval errors
                    continue

            # Execute actions (ordered)
            for act in (rule.get("do") or []):
                plan_delta = self._exec_action(act, event, current_bets or {})
                if plan_delta:
                    actions.extend(plan_delta)

        # 3) return the accumulated plan
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

    # --- internals ---

    def _ingest_event_side_effects(self, event: Dict[str, Any]) -> None:
        et = event.get("type")
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
            # increment rolls_since_point only when point is on
            if not self._ctrl.on_comeout and self._ctrl.point:
                self._ctrl.rolls_since_point += 1
        elif et == "seven_out":
            self._ctrl.on_comeout = True
            self._ctrl.point = None
            self._ctrl.rolls_since_point = 0
        elif et == "shooter_change":
            # no-op for counters; next roll will produce a comeout event
            pass

    def _exec_action(self, act: Any, event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict]:
        """
        Interpret a single action item. Returns a list of planned bet ops (may be empty).
        Supported forms:
          - "x = expr"
          - "x += expr" / "x -= expr"
          - "mode = 'Name'"
          - "apply_template('Name')"
          - "clear_bets()"
          - "log("message")"
        """
        if not isinstance(act, str):
            return []

        # apply_template('ModeName')
        m = _APPLY_TEMPLATE_RE.match(act)
        if m:
            mode_name = m.group(1)
            template = ((self.spec.get("modes") or {}).get(mode_name) or {}).get("template") or {}
            plan = _render_and_diff(template, self._ctrl, event, self.table_cfg, current_bets)
            return plan

        # clear_bets()
        if _CLEAR_RE.match(act):
            clears = [{"action": "clear", "bet_type": k} for k in sorted(current_bets.keys())]
            return clears

        # log("message")
        m = _LOG_RE.match(act)
        if m:
            self._ctrl.logs.append(m.group(1))
            return []

        # x += expr / x -= expr
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
            # ints where possible
            self._ctrl.vars[name] = int(newv) if float(newv).is_integer() else newv
            return []

        # x = expr  (also supports "mode = 'Name'")
        m = _ASSIGN_RE.match(act)
        if m:
            name, expr = m.group(1), m.group(2)
            if name == "mode":
                ctx = _mk_ctx(self._ctrl, event, self.table_cfg)
                try:
                    val = evaluate(expr, ctx, {})
                except EvalError:
                    return []
                self._ctrl.mode = str(val)
                return []
            else:
                ctx = _mk_ctx(self._ctrl, event, self.table_cfg)
                try:
                    val = evaluate(expr, ctx, {})
                except EvalError:
                    return []
                # normalize numeric types where clean
                if isinstance(val, (int, float)) and float(val).is_integer():
                    val = int(val)
                self._ctrl.vars[name] = val
                return []

        # unknown action -> ignore
        return []