# crapssim_control/controller.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .eval import evaluate as _eval
# FIX: use the runtime template module
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
    This class intentionally keeps a small public surface used by our adapter & tests:
      - update_bets(table) : pre-roll hook
      - after_roll(table, event) : post-roll hook
      - handle_event(event, current_bets) -> List[actions]
    """

    def __init__(self, spec: Dict[str, Any], table_cfg: Optional[Dict[str, Any]] = None) -> None:
        self.spec = spec or {}
        self._ctrl = _Ctrl.from_spec(spec, table_cfg)
        # sticky bookkeeping visible to rules via VarStore counters
        self._last_bets_snapshot: Dict[str, Dict] = {}

    # -------------------------
    # Public hooks
    # -------------------------

    def update_bets(self, table: Any) -> None:
        """
        Pre-roll hook. In our current unit tests we don't need to do anything here,
        but keeping this method satisfies the adapter contract.
        """
        return None

    def after_roll(self, table: Any, event: Dict[str, Any]) -> None:
        """
        Post-roll hook. We maintain a few counters commonly used by rules/specs.
        """
        vs = self._ctrl.vs
        ev = event.get("type") or event.get("event")

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
            # generic roll that isn't a comeout/point change
            vs.counters["rolls_since_point"] = vs.counters.get("rolls_since_point", 0) + 1

    # -------------------------
    # Event handling
    # -------------------------

    def handle_event(self, event: Dict[str, Any], current_bets: Optional[Dict[str, Dict]] = None) -> List[Dict]:
        """
        Evaluate rules for the given event and return a plan (list of actions).
        """
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

        # Guarantee deterministic clear-then-set for any sets that slipped through earlier phases
        actions = _ensure_clears_for_sets(actions)
        return actions

    # -------------------------
    # Internals
    # -------------------------

    def _ingest_event_side_effects(self, event: Dict[str, Any]) -> None:
        """Mirror a few event fields into counters so expressions can use them."""
        vs = self._ctrl.vs
        # Normalize key 'type'/'event'
        ev = event.get("type") or event.get("event")
        if ev:
            vs.counters["last_event"] = ev
        if "total" in event:
            vs.counters["last_total"] = int(event["total"])

    def _exec_action(self, action: Any, event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict]:
        """
        Execute a single action instruction from a rule. Returns a list of bet actions.
        Supported actions:
          - "apply_template('ModeName')"
          - variable expressions like "units = 10", "units += 5", etc. (no bet actions returned)
          - "mode = 'X'"
          - "clear_bets()"  (clears all active number-based bets)
        """
        if isinstance(action, str) and action.strip().startswith("apply_template"):
            # Extract mode name between quotes
            mode_name = _extract_first_string_literal(action) or self._ctrl.mode
            return self._apply_template(mode_name, event, current_bets)

        if isinstance(action, str) and action.strip().startswith("clear_bets"):
            return self._clear_all(current_bets)

        # Assignment / arithmetic to variables or mode
        # We allow expressions like "units = units + 5", "units *= 2", "mode = 'Regressed'"
        # Evaluate by delegating to our safe evaluator in the env
        _ = _eval(action, _eval_env(self._ctrl, event))
        # variable-only changes don't produce bet actions
        if action.replace(" ", "").startswith("mode=") or action.replace(" ", "").startswith("mode="):
            # keep self._ctrl.mode in sync if user directly sets mode var
            m = _extract_first_string_literal(action)
            if m:
                self._ctrl.mode = m
        return []

    def _apply_template(self, mode_name: str, event: Dict[str, Any], current_bets: Dict[str, Dict]) -> List[Dict]:
        spec_modes = self.spec.get("modes") or {}
        mode_def = spec_modes.get(mode_name) or {}
        template = mode_def.get("template") or {}

        state = _state_env_for_template(self._ctrl)
        desired = render_template(template, state, event, self._ctrl.table_cfg)
        # remember desired for any later diffs, if needed
        self._last_bets_snapshot = desired
        plan = diff_bets(current_bets or {}, desired)
        # Enrich with kind/number for convenience (doesn't affect engine)
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
    # very small helper to get 'X' or "X" out of a call-like string
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
    Build a safe evaluation environment for rule expressions.
    We expose three dicts:
      - vars: mutable user variables
      - system: table/system flags (bubble, table_level)
      - counters: derived counters (point, on_comeout, rolls_since_point, etc.)
    """
    vs = ctrl.vs

    env: Dict[str, Any] = {
        "vars": vs.user if vs.user else vs.variables,  # prefer user scope if present
        "system": vs.system,
        "counters": vs.counters,
        # helpers
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
        # convenience names used in examples/specs
        "mode": vs.user.get("mode", vs.variables.get("mode", "Main")),
    }

    # Keep 'mode' write-through by returning a small proxy setter via assignment handling.
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
    # The template renderer expects a flat state with both user vars and counters.
    state = {}
    state.update(vs.user if vs.user else vs.variables)
    state.update({
        "bubble": bool(vs.system.get("bubble", False)),
        "point": int(vs.counters.get("point", 0)),
        "on_comeout": bool(vs.counters.get("on_comeout", state.get("point", 0) == 0)),
    })
    return state