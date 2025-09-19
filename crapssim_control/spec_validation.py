from __future__ import annotations

from typing import Any, Dict, List


# -------------------------------------------------
# Public API
# -------------------------------------------------

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


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    """
    Return a flat list of 'hard' validation errors.
    (Existing tests expect exactly this signature and behavior.)
    """
    errors: List[str] = []

    # Required top-level sections
    required = ("table", "modes", "rules")
    for key in required:
        if key not in spec:
            errors.append(f"Missing required section: '{key}'")
            # Tests expect a friendlier message for 'modes' as well.
            if key == "modes":
                errors.append("You must define at least one mode.")

    # variables is optional but if present must be a dict
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
                # template values may be:
                # - number (amount),
                # - string (variable reference),
                # - object with at least 'amount' number
                for k, v in tmpl.items():
                    if isinstance(v, (int, float)):
                        continue
                    if isinstance(v, str):
                        continue
                    if isinstance(v, dict):
                        amt = v.get("amount")
                        if _is_number(amt):
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
                if not isinstance(r, dict):
                    errors.append(f"rules[{i}] must be an object")
                    continue
                on = r.get("on")
                do = r.get("do")
                if not isinstance(on, dict):
                    errors.append(f"rules[{i}].on must be an object")
                else:
                    ev = on.get("event")
                    if not isinstance(ev, str):
                        errors.append("on.event must be a string")
                if not isinstance(do, list):
                    errors.append(f"rules[{i}].do must be an array")
                else:
                    for j, step in enumerate(do):
                        if not isinstance(step, str):
                            errors.append(f"do[{j}] must be a string")

    # OPTIONAL: table_rules (Batch 2 shape-only checks)
    if "table_rules" in spec and spec.get("table_rules"):
        errors.extend(_validate_table_rules_block(spec["table_rules"]))

    return errors


# -------------------------------------------------
# Private helpers
# -------------------------------------------------

def _validate_table_rules_block(tr: Any) -> List[str]:
    errs: List[str] = []
    if not isinstance(tr, dict):
        return ["table_rules must be an object"]

    # enforcement
    enf = tr.get("enforcement")
    if enf is not None and enf not in ("warning", "strict"):
        errs.append("table_rules.enforcement must be 'warning' or 'strict'")

    # profile (optional string)
    prof = tr.get("profile")
    if prof is not None and not isinstance(prof, str):
        errs.append("table_rules.profile must be a string")

    # max
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

    # increments
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

    # allow
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