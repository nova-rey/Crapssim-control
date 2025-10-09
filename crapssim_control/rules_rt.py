# crapssim_control/rules_rt.py
from __future__ import annotations

"""
rules_rt.py — Runtime Rules (Phase 4 · Checkpoint 4)

Purpose
-------
Turn spec "rules" into Action Envelopes.

Supported (MVP + P4C2/P4C3/P4C4):
  • Event gating via rule["on"]["event"] in {"comeout","roll","point_established","seven_out"}
  • Optional boolean predicate rule["when"] evaluated against (state ⊕ event)
  • "do" steps (string OR object forms):
        - set <bet_type> <amount>
        - clear <bet_type>
        - press <bet_type> <amount>
        - reduce <bet_type> <amount>
        - switch_mode <ModeName>
        - setvar <VarName> <ExprOrNumber>        # NEW in P4C4

  Object step form (both keys supported for back-compat):
      { "action": "...", "bet": "place_6", "amount": 12, "notes": "..." }
      { "action": "...", "bet_type": "place_6", "amount": "units*2" }
      { "action": "switch_mode", "mode": "Aggressive" }
      { "action": "setvar", "var": "win_streak", "value": "win_streak+1" }  # NEW

Design notes
------------
- Fail open & quiet: invalid rules/steps are skipped; we do not raise.
- Amounts may be numeric literals or expressions (evaluated with eval_num()).
- switch_mode produces an envelope with bet_type=None, amount=None, notes=<mode>.
- setvar produces an envelope with action="setvar" and attaches {"var": ..., "value": ...}.
  (Controller applies setvars immediately in the same event.)
- Rule IDs:
    • prefer a non-empty "name" → id="rule:<name>"
    • else fall back to 1-based index → id="rule:#<index>"
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


# Local extension for P4C4
ACTION_SETVAR = "setvar"


# --------------------------- Public Entry Point --------------------------------- #

def apply_rules(
    rules: Optional[List[Dict[str, Any]]],
    state: Dict[str, Any],
    event: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Evaluate a list of rule dicts and return Action Envelopes for those that fire.
    """
    if not isinstance(rules, list) or not rules:
        return []

    ev_type = str((event or {}).get("type", "")).strip().lower()
    out: List[Dict[str, Any]] = []

    for idx, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            continue

        rid = _rule_id(rule, idx)

        # --- Event gating (required) ---
        on = rule.get("on") or {}
        if not isinstance(on, dict):
            continue
        want_event = str(on.get("event", "")).strip().lower()
        if not want_event or want_event != ev_type:
            # Spec validation enforces canonical values; here we keep it permissive.
            continue

        # --- Predicate (optional) ---
        cond_expr = rule.get("when")
        if cond_expr is not None:
            try:
                if not eval_bool(str(cond_expr), state, event):
                    continue
            except EvalError:
                # treat expression errors as False; skip quietly
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
    if isinstance(name, str):
        nm = name.strip()
        if nm:
            return f"rule:{nm}"
    return f"rule:#{one_based_index}"


def _parse_step_string(step: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Parse a minimal space-delimited step string into (action, key_or_bet, arg_or_none).

    Examples:
      "set place_6 12"          -> ("set", "place_6", "12")
      "clear place_6"           -> ("clear", "place_6", None)
      "press place_6 6"         -> ("press", "place_6", "6")
      "reduce place_8 6"        -> ("reduce", "place_8", "6")
      "switch_mode Aggressive"  -> ("switch_mode", None, "Aggressive")
      "setvar win_streak win_streak+1" -> ("setvar", "win_streak", "win_streak+1")
    """
    parts = str(step).strip().split()
    if not parts:
        return "", None, None
    action = parts[0].strip().lower()
    if action == ACTION_SWITCH_MODE:
        # everything after keyword is the mode name (can contain spaces)
        mode = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
        return action, None, (mode or None)
    if action == ACTION_SETVAR:
        var = parts[1].strip() if len(parts) > 1 else ""
        expr = parts[2].strip() if len(parts) > 2 else ""
        return action, (var or None), (expr or None)
    if len(parts) == 1:
        return action, None, None
    if len(parts) == 2:
        return action, parts[1], None
    # len >= 3 → treat third token (only) as amount/expression
    return action, parts[1], parts[2]


def _coerce_bet_key(step: Dict[str, Any]) -> Optional[str]:
    """
    Accept both 'bet' and 'bet_type' to remain compatible with older specs/tests.
    """
    bet = step.get("bet")
    if bet is None:
        bet = step.get("bet_type")
    if bet is None:
        return None
    return str(bet)


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
    # Dict form: {"action": "...", "bet"/"bet_type": "...", "amount": 10|"expr", "notes": "..."}
    if isinstance(step, dict):
        action = str(step.get("action", "")).strip().lower()

        # Allow standard actions + local extension 'setvar'
        if action not in ALLOWED_ACTIONS and action != ACTION_SETVAR:
            return None

        # ----- setvar (object form) -----
        if action == ACTION_SETVAR:
            var = step.get("var") or step.get("name")
            # Prefer explicit 'value', otherwise allow numeric 'amount', otherwise 'notes' text
            value = step.get("value") if "value" in step else (step.get("amount") if "amount" in step else step.get("notes"))
            env = make_action(
                ACTION_SETVAR,
                bet_type=None,
                amount=None,  # controller reads 'value' (or amount) and applies immediately
                source=SOURCE_RULE,
                id_=rule_id,
                notes=str(value) if value is not None else "",
            )
            # Attach explicit var/value so controller can apply immediately
            if isinstance(var, str) and var.strip():
                env["var"] = var.strip()
            if value is not None:
                env["value"] = value
            return env

        # ----- switch_mode (object form) -----
        if action == ACTION_SWITCH_MODE:
            notes = (step.get("notes") or "").strip()
            target = str(step.get("mode") or notes or "").strip()
            return make_action(
                ACTION_SWITCH_MODE,
                bet_type=None,
                amount=None,
                source=SOURCE_RULE,
                id_=rule_id,
                notes=target,
            )

        # ----- bet actions (object form) -----
        bet_type = _coerce_bet_key(step)
        amount = step.get("amount")
        notes = (step.get("notes") or "").strip()

        if action != ACTION_CLEAR and not bet_type:
            # set/press/reduce require a bet_type
            return None

        amt_val: Optional[float] = None
        if action != ACTION_CLEAR:
            if amount is None:
                return None
            try:
                if isinstance(amount, (int, float)):
                    amt_val = float(amount)
                else:
                    amt_val = float(eval_num(str(amount), state, event))
            except Exception:
                return None

        return make_action(
            action,
            bet_type=bet_type,
            amount=amt_val,
            source=SOURCE_RULE,
            id_=rule_id,
            notes=notes,
        )

    # String form
    if isinstance(step, str):
        action, key, arg = _parse_step_string(step)
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
                notes=str(arg or "").strip(),
            )

        if action == ACTION_SETVAR:
            var = key or ""
            value_expr = arg if arg is not None else ""
            env = make_action(
                ACTION_SETVAR,
                bet_type=None,
                amount=None,
                source=SOURCE_RULE,
                id_=rule_id,
                notes=str(value_expr).strip(),
            )
            if var:
                env["var"] = var
            if value_expr is not None:
                env["value"] = value_expr
            return env

        if action in (ACTION_SET, ACTION_CLEAR, ACTION_PRESS, ACTION_REDUCE):
            bet_type = key if isinstance(key, str) and key else None
            if action != ACTION_CLEAR and bet_type is None:
                return None

            amt_val: Optional[float] = None
            if action != ACTION_CLEAR:
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