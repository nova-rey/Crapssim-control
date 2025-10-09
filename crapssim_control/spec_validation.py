# crapssim_control/spec_validation.py
from __future__ import annotations

from typing import Any, Dict, List

from .events import CANONICAL_EVENT_TYPES  # includes shooter_change & bet_resolved


class SpecValidationError(Exception):
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def is_valid_spec(spec: Dict[str, Any]) -> bool:
    return len(validate_spec(spec)) == 0


def assert_valid_spec(spec: Dict[str, Any]) -> None:
    errs = validate_spec(spec)
    if errs:
        raise SpecValidationError(errs)


# Allowed action verbs for object-form steps
_ALLOWED_ACTIONS = {"set", "clear", "press", "reduce", "switch_mode"}
_ACTION_NEEDS_AMOUNT = {
    "set": True,
    "clear": False,
    "press": True,
    "reduce": True,
    "switch_mode": False,
}
# Legacy free-form starters (string steps) we allow without strict parsing
_FREEFORM_STARTERS = {"units"}  # e.g., "units 10"


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    """
    Return a flat list of 'hard' validation errors (no warnings).

    String `do` steps:
      • Accept free-form directives like "apply_template('Main')" (contain '(')
      • Accept legacy free-form starters like "units 10"
      • Heuristically flag obvious verb-like forms (e.g., "explode place_6 10")

    Object `do` steps:
      • Strictly validated (action/bet/amount as appropriate)
      • Accept both 'bet' and 'bet_type'
      • 'amount' may be a number OR a string expression (evaluated at runtime)
    """
    errors: List[str] = []

    # Required top-level sections
    required = ("table", "modes", "rules")
    for key in required:
        if key not in spec:
            errors.append(f"Missing required section: '{key}'")
            if key == "modes":
                errors.append("You must define at least one mode.")

    # variables
    if "variables" in spec and not isinstance(spec["variables"], dict):
        errors.append("variables must be an object")

    # table
    if "table" in spec and isinstance(spec["table"], dict):
        t = spec["table"]
        if "bubble" in t and not isinstance(t["bubble"], bool):
            errors.append("table.bubble must be a boolean")
        if "level" in t:
            if not _is_number(t["level"]):
                errors.append("table.level must be a number")
            elif float(t["level"]) <= 0:
                errors.append("table.level must be > 0")
    elif "table" in spec:
        errors.append("table must be an object")

    # modes
    if "modes" in spec:
        modes = spec["modes"]
        if not isinstance(modes, dict) or not modes:
            errors.append("You must define at least one mode.")
        else:
            for mname, mval in modes.items():
                if not isinstance(mval, dict):
                    errors.append(f"modes['{mname}'] must be an object")
                    continue
                if "template" not in mval:
                    errors.append(f"modes['{mname}'] is missing required key 'template'")
                    continue
                tmpl = mval["template"]
                if not isinstance(tmpl, dict):
                    errors.append(f"modes['{mname}'].template must be an object")
                    continue
                for k, v in tmpl.items():
                    if isinstance(v, (int, float)):
                        continue
                    if isinstance(v, str):
                        continue
                    if isinstance(v, dict):
                        amt = v.get("amount")
                        if _is_number(amt) or isinstance(amt, str):
                            continue
                    errors.append(
                        "template values must be a number/string or an object with 'amount'"
                    )

    # rules
    if "rules" in spec:
        rules = spec["rules"]
        if not isinstance(rules, list):
            errors.append("rules must be an array")
        else:
            for i, r in enumerate(rules):
                ctx = _rule_ctx(r, i)
                if not isinstance(r, dict):
                    errors.append(f"{ctx} must be an object")
                    continue

                # on.event
                on = r.get("on")
                if not isinstance(on, dict):
                    errors.append(f"{ctx}.on must be an object")
                else:
                    ev = on.get("event")
                    if not isinstance(ev, str):
                        errors.append(f"{ctx}.on.event must be a string")
                    else:
                        if ev not in CANONICAL_EVENT_TYPES:
                            allowed = ", ".join(sorted(CANONICAL_EVENT_TYPES))
                            errors.append(f"{ctx}.on.event must be one of {{{allowed}}} (got '{ev}')")

                # when (optional) must be string if present
                if "when" in r and not isinstance(r.get("when"), str):
                    errors.append(f"{ctx}.when must be a string")

                # do
                do = r.get("do")
                if not isinstance(do, list):
                    errors.append(f"{ctx}.do must be an array")
                else:
                    for j, step in enumerate(do):
                        step_ctx = f"{ctx}.do[{j}]"
                        if isinstance(step, str):
                            _validate_do_string(step, step_ctx, errors)
                        elif isinstance(step, dict):
                            _validate_do_object(step, step_ctx, errors)
                        else:
                            errors.append(f"{step_ctx} must be a string or an object")

    # OPTIONAL: table_rules (shape-only checks)
    if "table_rules" in spec and spec.get("table_rules"):
        errors.extend(_validate_table_rules_block(spec["table_rules"]))

    return errors


# ----------------------------- helpers -------------------------------------------

def _rule_ctx(rule: Any, idx: int) -> str:
    if isinstance(rule, dict):
        nm = rule.get("name")
        if isinstance(nm, str) and nm.strip():
            return f"rules['{nm.strip()}']"
    return f"rules[{idx}]"


def _validate_do_string(step: str, ctx: str, errors: List[str]) -> None:
    """
    Heuristic validation for *string* steps:
      • If it contains '(' → allow (free-form directive like apply_template('Main')).
      • If it starts with a known free-form starter (e.g., 'units') → allow.
      • Else, if it looks like "<word> <word> <amount>" and the first word is not
        a known action → flag as unknown action.
      • Otherwise accept.
    """
    s = str(step).strip()
    if not s:
        errors.append(f"{ctx} must be a non-empty string")
        return

    if "(" in s:
        return  # free-form call-like directives are allowed

    parts = s.split()
    first = parts[0].lower()

    # allow legacy free-form directives (e.g., "units 10")
    if first in _FREEFORM_STARTERS:
        return

    if len(parts) >= 3:
        if first.isalpha() and first not in _ALLOWED_ACTIONS:
            allowed = ", ".join(sorted(_ALLOWED_ACTIONS))
            errors.append(f"{ctx}: unknown action '{first}' (allowed: {allowed})")


def _validate_do_object(step: Dict[str, Any], ctx: str, errors: List[str]) -> None:
    """
    Object form:
        { "action": "set"|"clear"|"press"|"reduce"|"switch_mode",
          "bet" or "bet_type": "<bet_type>",   # not required for switch_mode
          "amount": <number|string>,            # required for set/press/reduce
          "mode": "<name>",                     # optional for switch_mode
          "notes": "<free text>" }              # optional
    """
    action = step.get("action")
    if not isinstance(action, str):
        errors.append(f"{ctx}.action must be a string")
        return
    action_lc = action.lower()
    if action_lc not in _ALLOWED_ACTIONS:
        allowed = ", ".join(sorted(_ALLOWED_ACTIONS))
        errors.append(f"{ctx}.action must be one of {{{allowed}}}")
        return

    # bet required for all except switch_mode
    if action_lc != "switch_mode":
        bet = step.get("bet", step.get("bet_type"))
        if not isinstance(bet, str) or not bet.strip():
            errors.append(f"{ctx}.bet must be a non-empty string for action '{action_lc}'")

    # amount requirements
    needs_amt = _ACTION_NEEDS_AMOUNT[action_lc]
    if needs_amt:
        if "amount" not in step:
            errors.append(f"{ctx}.amount is required for action '{action_lc}'")
        else:
            amt = step["amount"]
            if not (_is_number(amt) or isinstance(amt, str)):
                errors.append(f"{ctx}.amount must be a number or string expression")


def _validate_table_rules_block(tr: Any) -> List[str]:
    errs: List[str] = []
    if not isinstance(tr, dict):
        return ["table_rules must be an object"]

    enf = tr.get("enforcement")
    if enf is not None and enf not in ("warning", "strict"):
        errs.append("table_rules.enforcement must be 'warning' or 'strict'")

    prof = tr.get("profile")
    if prof is not None and not isinstance(prof, str):
        errs.append("table_rules.profile must be a string")

    max_blk = tr.get("max")
    if max_blk is not None and not isinstance(max_blk, dict):
        errs.append("table_rules.max must be an object")
    else:
        if isinstance(max_blk, dict):
            for k in ("pass", "place", "field"):
                v = max_blk.get(k)
                if v is not None and not _is_number(v):
                    errs.append(f"table_rules.max.{k} must be a number")
            odds = max_blk.get("odds")
            if odds is not None:
                if not isinstance(odds, dict):
                    errs.append("table_rules.max.odds must be an object")
                else:
                    typ = odds.get("type")
                    if typ is not None and not (typ in ("3_4_5x", "flat")):
                        errs.append("table_rules.max.odds.type must be '3_4_5x' or 'flat'")
                    if typ == "flat":
                        mult = odds.get("multiplier")
                        if mult is not None and not _is_number(mult):
                            errs.append("table_rules.max.odds.multiplier must be a number")

    inc_blk = tr.get("increments")
    if inc_blk is not None and not isinstance(inc_blk, dict):
        errs.append("table_rules.increments must be an object")
    else:
        if isinstance(inc_blk, dict):
            for k in ("pass", "field"):
                v = inc_blk.get(k)
                if v is not None and not _is_number(v):
                    errs.append(f"table_rules.increments.{k} must be a number")
            place = inc_blk.get("place")
            if place is not None and not isinstance(place, dict):
                errs.append("table_rules.increments.place must be an object")
            elif isinstance(place, dict):
                for pt, inc in place.items():
                    if not _is_number(inc):
                        errs.append(f"table_rules.increments.place.{pt} must be a number")

    allow_blk = tr.get("allow")
    if allow_blk is not None and not isinstance(allow_blk, dict):
        errs.append("table_rules.allow must be an object")
    else:
        if isinstance(allow_blk, dict):
            for k, v in allow_blk.items():
                if not isinstance(v, bool):
                    errs.append(f"table_rules.allow.{k} must be a boolean")

    return errs


def _is_number(x: Any) -> bool:
    try:
        float(x)
        return True
    except Exception:
        return False