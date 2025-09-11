from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

ALLOWED_EVENTS = {
    "comeout",
    "point_established",
    "roll",
    "seven_out",
    "shooter_change",
    "bet_resolved",
}


def _require_keys(d: Dict[str, Any], keys: Iterable[str], where: str, errors: List[str]) -> None:
    for k in keys:
        if k not in d:
            # Match tests' phrasings at top-level and modes
            if where == "spec" and k == "modes":
                errors.append("modes section is required")
            elif where == "spec" and k == "meta":
                errors.append("Missing key 'meta' in spec")
            elif where.startswith("modes[") and k == "template":
                errors.append("template is required")
            else:
                errors.append(f"Missing key '{k}' in {where}")


def _validate_table(table: Dict[str, Any], errors: List[str]) -> None:
    _require_keys(table, ("bubble", "level"), "table", errors)
    if "bubble" in table and not isinstance(table["bubble"], bool):
        errors.append("table.bubble must be bool")
    if "level" in table and not isinstance(table["level"], int):
        errors.append("table.level must be integer")
    elif "level" in table and isinstance(table["level"], int) and table["level"] <= 0:
        errors.append("table.level must be positive")
    if "odds_policy" in table and not isinstance(table["odds_policy"], str):
        errors.append("table.odds_policy must be str if present")


def _validate_template(tpl: Dict[str, Any], errors: List[str]) -> None:
    if not isinstance(tpl, dict):
        errors.append("mode.template must be an object")
        return
    for k, v in tpl.items():
        if k in ("place", "buy", "lay", "come", "dont_come"):
            if not isinstance(v, dict):
                errors.append(f"template.{k} must be an object mapping numbers to expressions")
        else:
            if not isinstance(v, str):
                errors.append(f"template.{k} expression must be string")


def _validate_modes(modes: Dict[str, Any], errors: List[str]) -> None:
    for name, body in modes.items():
        if not isinstance(body, dict):
            errors.append(f"modes['{name}'] must be object")
            continue
        _require_keys(body, ("template",), f"modes['{name}']", errors)
        if "template" in body:
            _validate_template(body["template"], errors)


def _validate_rule(rule: Dict[str, Any], errors: List[str]) -> None:
    _require_keys(rule, ("on", "do"), "rule", errors)
    if not isinstance(rule.get("on"), dict):
        errors.append("rule.on must be an object")
        return
    ev = rule["on"].get("event")
    if ev not in ALLOWED_EVENTS:
        errors.append(f"rule.on.event must be one of {sorted(ALLOWED_EVENTS)}")

    if "if" in rule and not isinstance(rule["if"], str):
        errors.append("rule.if must be a string expression")

    do = rule.get("do")
    if not isinstance(do, list) or not do:
        errors.append("do must be a list of strings")
    else:
        for a in do:
            if not isinstance(a, str):
                errors.append("do must be a list of strings")


def _validate_rules(rules: List[Dict[str, Any]], errors: List[str]) -> None:
    if not isinstance(rules, list):
        errors.append("rules must be an array")
        return
    for r in rules:
        if not isinstance(r, dict):
            errors.append("rules[] must be objects")
            continue
        _validate_rule(r, errors)


def validate_spec(spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a control spec. Returns (ok, errors) with messages matching test expectations.
    """
    errors: List[str] = []
    if not isinstance(spec, dict):
        return False, ["Spec must be a JSON object"]

    _require_keys(spec, ("meta", "table", "variables", "modes", "rules"), "spec", errors)

    if "table" in spec:
        _validate_table(spec["table"], errors)
    if "modes" in spec:
        _validate_modes(spec["modes"], errors)
    if "rules" in spec:
        _validate_rules(spec["rules"], errors)

    return (len(errors) == 0, errors)