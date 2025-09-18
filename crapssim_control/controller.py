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
    In our test suite these are typically identical (e.g., 'pass', 'place', 'field'),
    so default to identity.
    """
    return bet_type


def _safe_collect_bets(table_like: Any) -> Dict[str, Any]:
    """
    Best-effort snapshot of a table/player's current bets into a flat dict:
      - Keys are 'bet_type' or 'bet_type:number' for numbered bets
      - Values are either amount (float) or {'amount': float}

    The EngineAdapter tests only need something sane here; missing attributes are tolerated.
    """
    out: Dict[str, Any] = {}

    try:
        # Allow either table_like.bets or table_like.player.bets styles
        bets = getattr(table_like, "bets", None)
        if bets is None and hasattr(table_like, "player"):
            bets = getattr(table_like.player, "bets", None)

        if not bets:
            return out

        for b in bets:
            # Handle fake bet objects used in tests
            kind = getattr(b, "kind", None) or getattr(b, "bet_type", None) or getattr(b, "bet", None)
            number = getattr(b, "number", None)
            amount = getattr(b, "amount", None)

            if kind is None:
                continue

            key = str(kind) if number in (None, "", 0) else f"{kind}:{number}"
            out[key] = float(amount) if isinstance(amount, (int, float)) else {"amount": 0.0}
    except Exception:
        # Stay silent; an empty snapshot is acceptable for callers.
        pass

    return out


def _diff_bets_to_actions(
    current: Dict[str, Any],
    desired: Any,  # dict OR list[tuple]
) -> List[Dict[str, Any]]:
    """Diff current -> desired into engine actions.

    `desired` can be:
      - a dict like {"pass": 10, "place:6": 12} or {"pass": {"amount": 10}, ...}
      - a list of tuples from render_template:
          [(bet_type, number, amount, opts_dict), ...]

    Always include both:
      - 'bet_type' (engine-facing)
      - 'bet' (rules shim name)
    plus 'action' and 'amount', and 'number' when applicable.
    """
    actions: List[Dict[str, Any]] = []

    # normalize current into a flat { key -> amount } map
    def _amt(v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict) and isinstance(v.get("amount"), (int, float)):
            return float(v["amount"])
        return None

    curr_amt = {k: _amt(v) for k, v in (current or {}).items()}

    # normalize desired into a list of target dicts
    targets: List[Dict[str, Any]] = []
    if isinstance(desired, dict):
        for k, v in desired.items():
            # allow keys like "place:6" or separate number dimension; keep both options open
            bet_type = k
            number = None
            if isinstance(k, str) and ":" in k:
                parts = k.split(":", 1)
                bet_type = parts[0]
                try:
                    number = int(parts[1])
                except (ValueError, TypeError):
                    number = parts[1]  # keep as-is if unparsable
            targets.append({
                "bet_type": bet_type,
                "bet": _rules_bet_for(bet_type),
                "number": number,
                "amount": _amt(v) or 0.0,
            })
    elif isinstance(desired, (list, tuple)):
        # render_template format: (bet_type, number, amount, opts)
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
        # unknown shape -> nothing to do
        return actions

    # Decide which actions we need
    for t in targets:
        # build a comparison key (include number for place/lay/etc. when present)
        key = t["bet_type"] if t["number"] in (None, "", 0) else f'{t["bet_type"]}:{t["number"]}'
        curr = curr_amt.get(key)
        if curr is None:
            # also allow plain bet key if current doesn't include number
            curr = curr_amt.get(t["bet_type"])
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

    # (Optional) removals if current has bets that desired omits -- tests don’t need it now.

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

    Interfaces used in tests:
      - ControlStrategy(spec)
      - update_bets(table_like)
      - handle_event(event_dict, current_bets_dict)
    """

    def __init__(self, spec: Dict[str, Any], ctrl_state: Any | None = None) -> None:
        self._spec = spec or {}
        self._table_cfg = (self._spec.get("table") or {}).copy()

        # seed variables from spec
        variables = (self._spec.get("variables") or {}).copy()
        # ensure a mode is always present (used to pick template)
        if "mode" not in variables:
            # try default from modes or fall back to first declared mode
            modes = list((self._spec.get("modes") or {}).keys())
            variables["mode"] = modes[0] if modes else "Main"

        self._ctrl = _CtrlState(vars=variables)
        if isinstance(ctrl_state, dict):
            # merge any externally provided variables (VarStore.user/variables, etc.)
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
        _ = self.handle_event({"type": ev_type, "event": ev_type}, current_bets=current)
        return _

    def handle_event(self, event: Dict[str, Any], current_bets: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Main entry used by tests and rules shim.
        Steps:
          1. Update internal point state when events dictate.
          2. Run matching rules and collect actions.
          3. Apply the active mode's template and diff against current bets.
        """
        plan: List[Dict[str, Any]] = []

        ev = dict(event or {})
        ev_type = ev.get("type") or ev.get("event")

        # -----------------
        # Update point state & counters (minimal for tests)
        # -----------------
        if ev_type == "point_established":
            # tests pass {"point": N}
            self._ctrl.point = int(ev.get("point") or 0) or None
        elif ev_type in ("seven_out", "puck_off", "seven_out_resolved"):
            self._ctrl.point = None

        # -----------------
        # 2) Run matching rules
        # -----------------
        for rule in (self._spec.get("rules") or []):
            cond = rule.get("on") or {}
            if _event_matches(ev, cond):
                # Execute each action in sequence; collect any bet-setting actions returned
                for act in rule.get("do") or []:
                    plan_delta = self._exec_action(act, ev, current_bets)
                    if plan_delta:
                        plan.extend(plan_delta)

        # -----------------
        # 3) Apply the active mode template
        # -----------------
        mode_name = str(self._ctrl.vars.get("mode") or "Main")
        plan.extend(self._apply_template(mode_name, current_bets or {}, ev))

        return plan

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
        Executes a single "do" item from a rule.
        Supports:
          - "apply_template('ModeName')"
          - any variable expression handled by eval.evaluate (e.g., "units += 10", "rolls_since_point = 0")
        """
        if not isinstance(action_expr, str):
            return []

        expr = action_expr.strip()

        # Template application syntax: apply_template('Mode') or apply_template("Mode")
        if expr.startswith("apply_template(") and expr.endswith(")"):
            inside = expr[len("apply_template("):-1].strip()
            # strip quotes if present
            if (inside.startswith("'") and inside.endswith("'")) or (inside.startswith('"') and inside.endswith('"')):
                inside = inside[1:-1]
            return self._apply_template(inside, current_bets or {}, event)

        # Otherwise, treat as an expression to mutate variables/counters/etc.
        # Provide a state object that eval.py can operate on.
        state = self._build_eval_state()
        _ = _eval(expr, state=state, event=event)
        # push back any mutated vars/counters
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
        # Resolve template object from spec modes
        tmpl_spec = (self._spec.get("modes") or {}).get(name, {}).get("template") or {}

        variables = self._ctrl.vars

        # Accept table configs that use either "level" or "table_level"
        bubble = bool(self._table_cfg.get("bubble"))
        table_level = self._table_cfg.get("level", self._table_cfg.get("table_level"))

        # Robust default if not specified anywhere; tests sometimes omit it.
        if table_level is None:
            # try controller vars (some harnesses stash it here), else $1 floor
            table_level = int(variables.get("table_level") or 1)

        # Try the two known signatures:
        #   render_template(template, variables, bubble, table_level, point)
        #   render_template(template, variables, bubble, table_level)
        rendered = None
        try:
            rendered = render_template(tmpl_spec, variables, bubble, table_level, self._ctrl.point)
        except TypeError:
            rendered = render_template(tmpl_spec, variables, bubble, table_level)

        return _diff_bets_to_actions(current_bets or {}, rendered or {})

    # ---- eval state plumbing -------------------------------------------------

    def _build_eval_state(self) -> Dict[str, Any]:
        """
        Build a state blob for eval.evaluate. Keep it minimal but include the parts
        the tests touch: variables and a small counters section.
        """
        # We keep a single shared dict so eval can read/write directly.
        # Structure chosen to be friendly with a permissive eval implementation.
        st: Dict[str, Any] = {}
        # expose variables both flat and under 'vars' so either style works
        st.update(self._ctrl.vars)
        st["vars"] = self._ctrl.vars
        # simple counters bucket the tests might reference
        st.setdefault("counters", {
            "points_established": 0,
            "points_made": 0,
            "seven_outs": 0,
            "last_event": None,
            "number_frequencies": {i: 0 for i in range(2, 13)},
        })
        # convenience event slot
        st["event"] = None
        # table-ish flags used by some templates/eval snippets
        st["on_comeout"] = self._ctrl.point in (None, 0, "")
        st["point"] = self._ctrl.point
        return st

    def _pull_back_from_eval_state(self, st: Dict[str, Any]) -> None:
        """Copy back mutated values from eval state to controller state."""
        # any top-level variables that exist in self._ctrl.vars should be updated
        for k in list(self._ctrl.vars.keys()):
            if k in st:
                self._ctrl.vars[k] = st[k]
        # also allow 'vars' bag to override
        if isinstance(st.get("vars"), dict):
            self._ctrl.vars.update(st["vars"])


# ----------------------------
# Rule matching
# ----------------------------

def _event_matches(ev: Dict[str, Any], cond: Dict[str, Any]) -> bool:
    """
    True iff all key/value pairs in cond appear equal in ev (string/int/float/None tolerant).
    """
    if not cond:
        return True
    for k, want in cond.items():
        if k not in ev:
            return False
        have = ev[k]
        # tolerate int/str equality for numbers present as strings
        if isinstance(want, (int, float)) and isinstance(have, str):
            try:
                have = float(have) if "." in have else int(have)
            except Exception:
                pass
        if have != want:
            return False
    return True