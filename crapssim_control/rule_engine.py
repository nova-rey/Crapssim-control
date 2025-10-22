from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple


class RuleEngineState:
    def __init__(self) -> None:
        # rule_id -> dict(last_fired_roll, disabled, remaining_cooldown, scope_lock)
        self.rules: Dict[str, Dict[str, Any]] = {}

    def get(self, rid: str) -> Dict[str, Any]:
        st = self.rules.get(rid)
        if not st:
            st = {
                "last_fired_roll": None,
                "disabled": False,
                "remaining_cooldown": 0,
                "scope_lock": None,
            }
            self.rules[rid] = st
        return st

    def tick(self) -> None:
        for st in self.rules.values():
            remaining = int(st.get("remaining_cooldown", 0) or 0)
            if remaining > 0:
                st["remaining_cooldown"] = max(0, remaining - 1)


class RuleEngine:
    """
    Drives WHEN/THEN rules over snapshots.
    Expects rules with fields:
      id, when (str), then {verb,args}, scope ("roll"|"hand"|"session"), cooldown (int), once (bool), _compiled (AST)
    """

    def __init__(self, rules: List[Dict[str, Any]]):
        self.rules = list(rules)
        self.state = RuleEngineState()
        self._group_seq = 0

    def _scope_key(self, scope: str, snapshot: Dict[str, Any]) -> Tuple[str, int]:
        # Use roll counters for scoping decisions
        hand_id = int(snapshot.get("hand_id", 0) or 0)
        roll_in_hand = int(snapshot.get("roll_in_hand", 0) or 0)
        if scope == "session":
            return ("session", 0)
        if scope == "hand":
            return ("hand", hand_id)
        return ("roll", roll_in_hand)

    def evaluate(
        self, snapshot: Dict[str, Any], trace_enabled: bool = False
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Evaluate rules and optionally emit DSL traces."""

        actions: List[Dict[str, Any]] = []
        traces: List[Dict[str, Any]] = []
        self.state.tick()

        self._group_seq += 1
        why_group = f"rulegrp-{self._group_seq}"

        for r in self.rules:
            rid = r.get("id") or f"rule_{r.get('then', {}).get('verb', 'unknown')}"
            scope = (r.get("scope") or "roll").lower()
            cooldown = int(r.get("cooldown", 0) or 0)
            once = bool(r.get("once", False))

            st = self.state.get(rid)
            if st.get("disabled"):
                continue
            remaining_cd = int(st.get("remaining_cooldown", 0) or 0)
            if remaining_cd > 0:
                continue

            scope_key = self._scope_key(scope, snapshot)
            if scope != "roll":
                prev_lock = st.get("scope_lock")
                if prev_lock is not None and prev_lock != scope_key:
                    st["scope_lock"] = None
                    prev_lock = None
                if prev_lock == scope_key:
                    continue

            ast = r.get("_compiled")
            if ast is None:
                continue

            from .dsl_eval import _eval_node  # lazy import to avoid circulars

            try:
                fire = bool(_eval_node(ast, snapshot))
            except Exception:
                fire = False

            if trace_enabled:
                now = datetime.utcnow().isoformat()
                why = f"WHEN ({r.get('when', '')}) → {'True' if fire else 'False'}"
                traces.append(
                    {
                        "type": "dsl_trace",
                        "rule_id": rid,
                        "when_expr": r.get("when", ""),
                        "evaluated_true": fire,
                        "why": why,
                        "actions": [r.get("then", {}).get("verb")],
                        "roll_id": snapshot.get("roll_in_hand", 0),
                        "timestamp": now,
                    }
                )

            if not fire:
                continue

            then = r.get("then", {})
            verb = then.get("verb") if isinstance(then, dict) else None
            args = dict(then.get("args", {})) if isinstance(then, dict) else {}
            if not verb:
                continue

            st["last_fired_roll"] = snapshot.get("roll_in_hand")
            if once:
                st["disabled"] = True
            if cooldown > 0:
                st["remaining_cooldown"] = cooldown + 1
            if scope != "roll":
                st["scope_lock"] = scope_key

            args.setdefault("_why_group", why_group)
            actions.append(
                {
                    "verb": verb,
                    "args": args,
                    "_rule_id": rid,
                    "_why_group": why_group,
                    "_when": r.get("when", ""),
                }
            )

        return actions, traces
