# crapssim_control/controller.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .eval import evaluate as _eval
from .templates_rt import render_template, diff_bets
from .varstore import VarStore


# -------------------------
# Small helpers
# -------------------------

_KIND_ALIASES = {
    "pass_line": ("pass", None),
    "dont_pass": ("dont_pass", None),
    "come": ("come", None),
    "dont_come": ("dont_come", None),
    "field": ("field", None),
}

def _bet_type_to_kind_number(bt: str) -> Tuple[str, Optional[int]]:
    """
    Map normalized bet_type strings to (kind, number).
    Examples:
      'place_6'   -> ('place', 6)
      'lay_10'    -> ('lay', 10)
      'pass_line' -> ('pass', None)
    """
    if bt in _KIND_ALIASES:
        return _KIND_ALIASES[bt]
    if "_" in bt:
        k, tail = bt.split("_", 1)
        try:
            n = int(tail)
            return k, n
        except ValueError:
            return bt, None
    return bt, None


def _ensure_clears_for_sets(actions: List[Dict]) -> List[Dict]:
    """Ensure a clear exists for every set; if missing, insert it just before the set."""
    out: List[Dict] = []
    for a in actions:
        if a.get("action") == "set":
            bt = a["bet_type"]
            if not (out and out[-1].get("action") == "clear" and out[-1].get("bet_type") == bt):
                k, n = _bet_type_to_kind_number(bt)
                out.append({"action": "clear", "bet_type": bt, "kind": k, "number": n})
            out.append(a)
        else:
            out.append(a)
    return out


def _normalize_event_keys(ev: Dict[str, Any]) -> Dict[str, Any]:
    """Make sure both 'event' and 'type' keys exist and match."""
    evn = dict(ev or {})
    if "event" not in evn and "type" in evn:
        evn["event"] = evn["type"]
    if "type" not in evn and "event" in evn:
        evn["type"] = evn["event"]
    return evn


def _desugar_augassign(expr: str) -> str:
    """
    Turn 'x += 1' into 'x = x + 1' (and friends) so our safe eval (mode='eval') can parse it.
    Only supports a simple identifier on the LHS.
    """
    s = expr.strip()
    ops = [("+=", "+"), ("-=", "-"), ("*=", "*"), ("/=", "/"), ("//=", "//"), ("%=", "%")]
    for op, sym in ops:
        if op in s:
            lhs, rhs = s.split(op, 1)
            name = lhs.strip()
            if name.replace("_", "").isalnum():  # basic guard; we expect a simple name
                return f"{name} = {name} {sym} ({rhs.strip()})"
    return expr


# -------------------------
# Internal controller state
# -------------------------

@dataclass
class _Ctrl:
    spec: Dict[str, Any]
    table_cfg: Dict[str, Any]
    vs: VarStore = field(default_factory=lambda: VarStore({}, {}, {}))

    @classmethod
    def from_spec(cls, spec: Dict[str, Any], table_cfg: Optional[Dict[str, Any]] = None) -> "_Ctrl":
        vs = VarStore.from_spec(spec)
        sys = {
            "bubble": bool((table_cfg or spec.get("table", {})).get("bubble", False)),
            "table_level": int((table_cfg or spec.get("table", {})).get("level", 10)),
        }
        vs.system = sys
        return cls(spec=spec, table_cfg=(table_cfg or spec.get("table") or {}), vs=vs)

    # convenience mirrors for tests / external shims
    @property
    def mode(self) -> str:
        return str(self.vs.user.get("mode") or self.vs.variables.get("mode") or "Main")

    @mode.setter
    def mode(self, m: str) -> None:
        # prefer user scope; fall back to variables for legacy tests
        if "mode" in self.vs.user:
            self.vs.user["mode"] = m
        else:
            self.vs.variables["mode"] = m


# -------------------------
# Public Strategy
# -------------------------

class ControlStrategy:
    """
    Runtime that executes a SPEC's rules and templates to produce bet actions.
    Public surface (used by tests/adapter):
      - update_bets(table)
      - after_roll(table, event)
      - handle_event(event, current_bets) -> List[actions]
      - state_snapshot() -> Dict
    """

    def __init__(self, spec: Dict[str, Any], table_cfg: Optional[Dict[str, Any]] = None) -> None:
        self.spec = spec or {}
        self._ctrl = _Ctrl.from_spec(spec, table_cfg)
        self._last_bets_snapshot: Dict[str, Dict] = {}

    # -------------------------
    # Public hooks
    # -------------------------

    def update_bets(self, table: Any) -> None:
        return None

    def after_roll(self, table: Any, event: Dict[str, Any]) -> None:
        vs = self._ctrl.vs
        ev = (event.get("type") or event.get("event"))

        if ev == "comeout":
            vs.counters["rolls_since_point"] = 0
            vs.counters["on_comeout"] = True
            vs.counters["point"] = 0
        elif ev == "point_established":
            vs.counters["on_comeout"] = False
            vs.counters["point"] = int(event.get("point") or 0)
            vs.counters["rolls_since_point"] = 0
            vs.counters["points_established"] = vs.counters.get("points_established", 0) + 1
        elif ev == "seven_out":
            vs.counters["rolls_since_point"] = 0
            vs.counters["point"] = 0
            vs.counters["on_comeout"] = True
            vs.counters["seven_outs"] = vs.counters.get("seven_outs", 0) + 1
        elif ev == "roll":
            vs.counters["rolls_since_point"] = vs.counters.get("rolls_since_point", 0) + 1

    def state_snapshot(self) -> Dict[str, Any]:
        """Provide a minimal snapshot used by tests."""
        vs = self._ctrl.vs
        return {
            "mode": self._ctrl.mode,
            "vars": (vs.user if vs.user else vs.variables).copy(),
            "point": int(vs.counters.get("point", 0)),
            "on_comeout": bool(vs.counters.get("on_comeout", True if int(vs.counters.get("point", 0)) == 0 else False)),
            "rolls_since_point": int(vs.counters.get("rolls_since_point", 0)),
        }

    # -------------------------
    # Event handling
    # -------------------------

    def handle_event(self, event: Dict[str, Any], current_bets: Optional[Dict[str, Dict]] = None) -> List[Dict]:
        """
        Evaluate rules for the given event and return a plan (list of actions).
        Accepts either {'type': ...} or {'event': ...}.
        """
        event = _normalize_event_keys(event)
        self._ingest_event_side_effects(event)

        actions: List[Dict] = []
        for rule in (self.spec.get("rules") or []):
            on = rule.get("on") or {}
            if not _event_matches(on, event):
                continue

            cond = rule.get("if")
            if cond is not None:
                if not _eval(cond, _eval_env(self._ctrl, event)):
                    continue

            for act in (rule.get("do") or []):
                plan_delta = self._exec_action(act, event, current_bets or {})
                if plan_delta:
                    actions.extend(plan_delta)

        # Deterministic clear-then-set
        actions = _ensure_clears_for_sets(actions)
        return actions

    # -------------------------
    # Internals
    # -------------------------

    def _ingest_event_side_effects(self, event: Dict[str, Any]) -> None:
        vs = self._ctrl.vs
        ev = event.get("type") or event.get("event")
        if ev:
            vs.counters["last_event"] = ev
        if "total" in event:
            vs.counters["last_total"] = int(event["total"])

    def _exec_action(self, action: Any, event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict]:
        """
        Execute a single action:
          - "apply_template('ModeName')"
          - "clear_bets()"
          - variable expressions: "units = 10", "units += 5", "mode = 'X'", etc.
        """
        if isinstance(action, str) and action.strip().startswith("apply_template"):
            mode_name = _extract_first_string_literal(action) or self._ctrl.mode
            return self._apply_template(mode_name, event, current_bets)

        if isinstance(action, str) and action.strip().startswith("clear_bets"):
            return self._clear_all(current_bets)

        # Variable update: support augmented assignment
        if isinstance(action, str):
            expr = _desugar_augassign(action)
            _ = _eval(expr, _eval_env(self._ctrl, event))
            # keep mode mirror in sync if user assigns to it
            if expr.replace(" ", "").startswith("mode="):
                m = _extract_first_string_literal(expr)
                if m:
                    self._ctrl.mode = m
        return []

    def _apply_template(self, mode_name: str, event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict]:
        spec_modes = self.spec.get("modes") or {}
        mode_def = spec_modes.get(mode_name) or {}
        template = mode_def.get("template") or {}

        state = _state_env_for_template(self._ctrl)
        desired = render_template(template, state, event, self._ctrl.table_cfg)
        self._last_bets_snapshot = desired
        plan = diff_bets(current_bets or {}, desired)
        for a in plan:
            bt = a.get("bet_type")
            if bt:
                k, n = _bet_type_to_kind_number(bt)
                a.setdefault("kind", k)
                if n is not None:
                    a.setdefault("number", n)
        return plan

    def _clear_all(self, current_bets: Dict[str, Dict]) -> List[Dict]:
        plan: List[Dict] = []
        for bt in sorted(current_bets.keys()):
            k, n = _bet_type_to_kind_number(bt)
            plan.append({"action": "clear", "bet_type": bt, "kind": k, "number": n})
        return plan


# -------------------------
# Pure functions
# -------------------------

def _event_matches(on: Dict[str, Any], ev: Dict[str, Any]) -> bool:
    """All key/value pairs in `on` must match `ev`."""
    for k, v in on.items():
        if ev.get(k) != v:
            return False
    return True


def _extract_first_string_literal(s: str) -> Optional[str]:
    q1 = s.find("'")
    q2 = s.find('"')
    q = None
    if q1 != -1 and (q2 == -1 or q1 < q2):
        q = "'"
    elif q2 != -1:
        q = '"'
    if q is None:
        return None
    start = s.find(q) + 1
    end = s.find(q, start)
    if start > 0 and end > start:
        return s[start:end]
    return None


def _eval_env(ctrl: _Ctrl, event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a safe environment for rule expressions.
    Expose:
      - vars: mutable user variables (prefer user scope if present)
      - system: table/system flags (bubble, table_level)
      - counters: derived counters (point, on_comeout, rolls_since_point, etc.)
      - mode: proxy object reflecting current mode (stringifiable)
    """
    vs = ctrl.vs

    env: Dict[str, Any] = {
        "vars": vs.user if vs.user else vs.variables,
        "system": vs.system,
        "counters": vs.counters,
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
    }

    class _ModeProxy:
        def __init__(self, _ctrl: _Ctrl) -> None:
            self._ctrl = _ctrl
        def __repr__(self) -> str:
            return self._ctrl.mode
        def __str__(self) -> str:
            return self._ctrl.mode

    env["mode"] = _ModeProxy(ctrl)
    return env


def _state_env_for_template(ctrl: _Ctrl) -> Dict[str, Any]:
    vs = ctrl.vs
    state = {}
    state.update(vs.user if vs.user else vs.variables)
    state.update({
        "bubble": bool(vs.system.get("bubble", False)),
        "point": int(vs.counters.get("point", 0)),
        "on_comeout": bool(vs.counters.get("on_comeout", state.get("point", 0) == 0)),
    })
    return state