# crapssim_control/spec.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional

ALLOWED_EVENTS = {
    "comeout",
    "point_established",
    "roll",
    "seven_out",
    "point_made",
    "bet_resolved",
    "shooter_change",
}

# Known top-level keys (others are ignored but kept forward-compatible)
TOP_KEYS = {"meta", "table", "variables", "modes", "rules"}

# Template keys we recognize in v0 (extra keys are allowed for forward-compat)
TEMPLATE_SCALARS = {
    "pass", "dont_pass", "field", "come", "dont_come",
    # odds (flat forms; engine-specific actions will interpret these)
    "odds", "dont_odds", "come_odds", "dont_come_odds",
}
TEMPLATE_NUMBERED = {
    "place",      # {"6": "expr", "8": "expr", ...}
    "place_dc",   # {"6": "expr", ...} -- future-proof
}

def _err(errors: List[str], msg: str) -> None:
    errors.append(msg)

def _is_intlike(x: Any) -> bool:
    try:
        int(x)
        return True
    except Exception:
        return False

def _validate_table(tbl: Any, errors: List[str], path: str = "table") -> None:
    if tbl is None:
        return
    if not isinstance(tbl, dict):
        _err(errors, f"{path} must be an object")
        return
    if "bubble" in tbl and not isinstance(tbl["bubble"], bool):
        _err(errors, f"{path}.bubble must be boolean")
    if "level" in tbl and not isinstance(tbl["level"], int):
        _err(errors, f"{path}.level must be integer")
    if "odds_policy" in tbl and not (isinstance(tbl["odds_policy"], (int, str))):
        _err(errors, f"{path}.odds_policy must be int or string (e.g. '3-4-5x')")

def _validate_variables(vars_: Any, errors: List[str], path: str = "variables") -> None:
    if vars_ is None:
        return
    if not isinstance(vars_, dict):
        _err(errors, f"{path} must be an object")
        return
    # values must be JSON-serializable; we only lightly check types
    for k, v in vars_.items():
        if not isinstance(k, str):
            _err(errors, f"{path} keys must be strings: got {k!r}")
        if not isinstance(v, (int, float, str, bool, type(None))):
            _err(errors, f"{path}.{k} has unsupported type {type(v).__name__}")

def _validate_template_dict(tpl: Any, errors: List[str], path: str) -> None:
    if not isinstance(tpl, dict):
        _err(errors, f"{path} must be an object")
        return

    for k, v in tpl.items():
        if k in TEMPLATE_SCALARS:
            if not isinstance(v, (int, float, str)):
                _err(errors, f"{path}.{k} must be number or expression string")
        elif k in TEMPLATE_NUMBERED:
            if not isinstance(v, dict):
                _err(errors, f"{path}.{k} must be an object mapping numbers to expressions")
            else:
                for nk, nv in v.items():
                    if not (isinstance(nk, str) and _is_intlike(nk)):
                        _err(errors, f"{path}.{k} key {nk!r} must be a number (as string)")
                    if not isinstance(nv, (int, float, str)):
                        _err(errors, f"{path}.{k}.{nk} must be number or expression string")
        else:
            # Forward-compatible: allow unknown keys but require values be simple
            if not isinstance(v, (int, float, str, dict)):
                _err(errors, f"{path}.{k} has unsupported type {type(v).__name__}")

def _validate_modes(modes: Any, errors: List[str], path: str = "modes") -> None:
    if modes is None:
        return
    if not isinstance(modes, dict):
        _err(errors, f"{path} must be an object")
        return
    for name, obj in modes.items():
        if not isinstance(name, str):
            _err(errors, f"{path} keys must be strings (mode names)")
        if not isinstance(obj, dict):
            _err(errors, f"{path}.{name} must be an object")
            continue
        tpl = obj.get("template")
        if tpl is None:
            _err(errors, f"{path}.{name}.template is required")
        else:
            _validate_template_dict(tpl, errors, f"{path}.{name}.template")

def _validate_rule(rule: Any, errors: List[str], idx: int) -> None:
    base = f"rules[{idx}]"
    if not isinstance(rule, dict):
        _err(errors, f"{base} must be an object")
        return
    # on
    on = rule.get("on")
    if not isinstance(on, dict):
        _err(errors, f"{base}.on must be an object")
    else:
        ev = on.get("event")
        if ev not in ALLOWED_EVENTS:
            _err(errors, f"{base}.on.event must be one of {sorted(ALLOWED_EVENTS)}, got {ev!r}")
        # allow extra qualifiers like bet/result/number
        for k, v in on.items():
            if k == "event":
                continue
            # Light type checks
            if k in {"bet", "result"} and not isinstance(v, str):
                _err(errors, f"{base}.on.{k} must be a string")
            if k in {"point", "number"} and not isinstance(v, int):
                _err(errors, f"{base}.on.{k} must be an integer")

    # if (expression string)
    if_cond = rule.get("if")
    if if_cond is not None and not isinstance(if_cond, str):
        _err(errors, f"{base}.if must be a string expression if present")

    # do (list of action strings)
    do = rule.get("do")
    if not isinstance(do, list) or not all(isinstance(x, str) for x in do):
        _err(errors, f"{base}.do must be a list of strings")

def _validate_rules(rules: Any, errors: List[str], path: str = "rules") -> None:
    if rules is None:
        return
    if not isinstance(rules, list):
        _err(errors, f"{path} must be an array")
        return
    for i, r in enumerate(rules):
        _validate_rule(r, errors, i)

def validate_spec(spec: Dict[str, Any], *, raise_on_error: bool = False) -> Tuple[bool, List[str]]:
    """
    Lightweight structural validation for v0 specs.
    Returns (ok, errors). If raise_on_error=True, raises ValueError on errors.
    """
    errors: List[str] = []

    if not isinstance(spec, dict):
        _err(errors, "Spec must be a JSON object")
        ok = False
        if raise_on_error:
            raise ValueError("; ".join(errors))
        return False, errors

    # Top-level keys (we don't forbid extras)
    for k in spec.keys():
        if not isinstance(k, str):
            _err(errors, f"Top-level key {k!r} must be a string")

    # Sections
    _validate_table(spec.get("table"), errors, "table")
    _validate_variables(spec.get("variables"), errors, "variables")
    _validate_modes(spec.get("modes"), errors, "modes")
    _validate_rules(spec.get("rules"), errors, "rules")

    # Minimal expectations
    if "variables" not in spec:
        _err(errors, "variables section is required")
    if "modes" not in spec:
        _err(errors, "modes section is required (with at least one mode + template)")
    if "rules" not in spec:
        _err(errors, "rules section is required (can be empty list)")

    ok = len(errors) == 0
    if (not ok) and raise_on_error:
        raise ValueError("; ".join(errors))
    return ok, errors