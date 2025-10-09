# crapssim_control/rules_rt.py
from __future__ import annotations

"""
rules_rt.py — Runtime Rules (Phase 3 · Checkpoint 1: MVP)

Purpose
-------
Turn spec "rules" into Action Envelopes. This MVP supports:
  • Event gating via rule["on"]["event"] in {"comeout","roll","point_established","seven_out"}
  • Optional boolean predicate rule["when"] evaluated against (state ⊕ event)
  • Basic "do" steps:
        - set <bet_type> <amount>
        - clear <bet_type>
        - press <bet_type> <amount>
        - reduce <bet_type> <amount>
        - switch_mode <ModeName>
    Steps may be provided as simple space-delimited strings (MVP form) or
    as dicts with explicit keys {"action","bet_type","amount","notes"}.

Design notes
------------
- We fail *open and quiet*: invalid rules/steps are skipped; we never raise.
- Amounts may be numeric literals or expressions (evaluated with eval_num()).
- switch_mode produces an envelope with bet_type=None, amount=None, notes=mode.
- Rule IDs:
    • prefer a non-empty "name" field → id="rule:<name>"
    • else fall back to 1-based index   → id="rule:#<index>"

This module intentionally does NOT mutate controller state; it only returns
envelopes. Controller decides how to apply them (Phase 3C2) and CSV logger
will serialize them (Phase 3C3).
"""

from typing import Any, Dict, List, Optional, Tuple

from .actions import (
    make_action,
    SOURCE_RULE,
    ACTION_SET,
    ACTION_CLEAR,
    ACTION_PRESS,
    ACTION_REDUCE,
    ACTION_SWITCH_MODE,
    ALLOWED_ACTIONS,
)
from .eval import eval_bool, eval_num, EvalError


# --------------------------- Public Entry Point --------------------------------- #

def apply_rules(
    rules: Optional[List[Dict[str, Any]]],
    state: Dict[str, Any],
    event: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Evaluate a list of rule dicts and return Action Envelopes for those that fire.

    Parameters
    ----------
    rules : list[dict] | None
        Strategy rules from the spec. Missing/invalid → no actions.
    state : dict
        Evaluation state (table cfg + user variables + controller snapshot).
    event : dict
        Event context (e.g., {"type": "roll", "total": 6, ...}).

    Returns
    -------
    list[dict]
        List of Action Envelopes (schema in actions.py). Empty on no matches.
    """
    if not isinstance(rules, list) or not rules:
        return []

    ev_type = str((event or {}).get("type", "")).strip().lower()
    out: List[Dict[str, Any]] = []

    for idx, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            continue

        rid = _rule_id(rule, idx)

        # --- Event gating (required in MVP) ---
        on = rule.get("on") or {}
        if not isinstance(on, dict):
            continue
        want_event = str(on.get("event", "")).strip().lower()
        if not want_event or want_event != ev_type:
            # Non-matching or missing event → skip rule
            continue

        # --- Predicate (optional) ---
        cond_expr = rule.get("when")
        if cond_expr is not None:
            try:
                if not eval_bool(str(cond_expr), state, event):
                    continue
            except EvalError:
                # On expression error, treat as False (rule doesn't fire)
                continue

        # --- Steps ---
        steps = rule.get("do")
        if not isinstance(steps, list):
            continue

        for step in steps:
            env = _step_to_envelope(step, state, event, rule_id=rid)
            if env is not None:
                out.append(env)

    return out


# ------------------------------ Helpers ---------------------------------------- #

def _rule_id(rule: Dict[str, Any], one_based_index: int) -> str:
    name = rule.get("name")
    if isinstance(name, str) and name.strip():
        return f"rule:{name.strip()}"
    return f"rule:#{one_based_index}"


def _parse_step_string(step: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Parse a minimal space-delimited step string into (action, bet_or_none, arg_or_none).

    Examples:
      "set place_6 12"          -> ("set", "place_6", "12")
      "clear place_6"           -> ("clear", "place_6", None)
      "press place_6 6"         -> ("press", "place_6", "6")
      "reduce place_8 6"        -> ("reduce", "place_8", "6")
      "switch_mode Aggressive"  -> ("switch_mode", None, "Aggressive")
    """
    parts = str(step).strip().split()
    if not parts:
        return "", None, None
    action = parts[0].lower()
    if action == ACTION_SWITCH_MODE:
        # everything after keyword is the mode name (can contain spaces)
        mode = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
        return action, None, mode or None
    if len(parts) == 1:
        return action, None, None
    if len(parts) == 2:
        return action, parts[1], None
    # len >= 3 → treat third token (only) as amount/expression
    return action, parts[1], parts[2]


def _step_to_envelope(
    step: Any,
    state: Dict[str, Any],
    event: Dict[str, Any],
    *,
    rule_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Convert a single step (string or dict) to an Action Envelope.
    Unknown/invalid steps return None (quietly).
    """
    # Dict form: {"action": "...", "bet_type": "...", "amount": 10, "notes": "..."}
    if isinstance(step, dict):
        action = str(step.get("action", "")).lower()
        if action not in ALLOWED_ACTIONS:
            return None

        bet_type = step.get("bet_type")
        if bet_type is not None:
            bet_type = str(bet_type)

        amount = step.get("amount")
        amt_val: Optional[float] = None
        if amount is not None:
            # Allow numeric or expression strings
            try:
                if isinstance(amount, (int, float)):
                    amt_val = float(amount)
                else:
                    amt_val = float(eval_num(str(amount), state, event))
            except Exception:
                amt_val = None

        notes = step.get("notes") or ""
        if action == ACTION_SWITCH_MODE:
            # Notes carries the target mode in MVP
            target = str(step.get("mode") or notes or "").strip()
            return make_action(
                ACTION_SWITCH_MODE,
                bet_type=None,
                amount=None,
                source=SOURCE_RULE,
                id_=rule_id,
                notes=target,
            )

        return make_action(
            action,
            bet_type=bet_type,
            amount=amt_val,
            source=SOURCE_RULE,
            id_=rule_id,
            notes=str(notes),
        )

    # String form
    if isinstance(step, str):
        action, bet, arg = _parse_step_string(step)
        if not action:
            return None

        if action == ACTION_SWITCH_MODE:
            # arg = ModeName (can be empty -> still envelope with empty notes)
            return make_action(
                ACTION_SWITCH_MODE,
                bet_type=None,
                amount=None,
                source=SOURCE_RULE,
                id_=rule_id,
                notes=str(arg or ""),
            )

        if action in (ACTION_SET, ACTION_CLEAR, ACTION_PRESS, ACTION_REDUCE):
            bet_type = bet if isinstance(bet, str) and bet else None
            if action != ACTION_CLEAR and bet_type is None:
                # set/press/reduce require a bet_type
                return None

            amt_val: Optional[float] = None
            if action != ACTION_CLEAR:
                # amount is required for set/press/reduce
                if arg is None or str(arg).strip() == "":
                    return None
                try:
                    amt_val = float(eval_num(str(arg), state, event))
                except Exception:
                    return None

            return make_action(
                action,
                bet_type=bet_type,
                amount=amt_val,
                source=SOURCE_RULE,
                id_=rule_id,
                notes="",
            )

        # Unknown action keyword → ignore
        return None

    # Unsupported step type
    return None