# crapssim_control/spec.py
from __future__ import annotations

from typing import Any, Dict, Iterable

REQUIRED_TOP_LEVEL_KEYS: tuple[str, ...] = ("meta", "table", "variables", "modes", "rules")
ALLOWED_EVENTS: set[str] = {
    "comeout",
    "point_established",
    "roll",
    "seven_out",
    "bet_resolved",
    "shooter_change",
}

def _require_keys(d: Dict[str, Any], keys: Iterable[str], where: str) -> None:
    for k in keys:
        if k not in d:
            raise ValueError(f"Missing key '{k}' in {where}")

def _validate_meta(meta: Dict[str, Any]) -> None:
    _require_keys(meta, ("version", "name"), "meta")
    if not isinstance(meta["version"], int):
        raise ValueError("meta.version must be int")
    if not isinstance(meta["name"], str) or not meta["name"].strip():
        raise ValueError("meta.name must be non-empty string")

def _validate_table(table: Dict[str, Any]) -> None:
    _require_keys(table, ("bubble", "level"), "table")
    if not isinstance(table["bubble"], bool):
        raise ValueError("table.bubble must be bool")
    if not isinstance(table["level"], int) or table["level"] <= 0:
        raise ValueError("table.level must be positive int")
    # optional
    if "odds_policy" in table:
        if table["odds_policy"] not in (None, "none", "2x", "5x", "3-4-5x"):
            raise ValueError("table.odds_policy must be one of: none, 2x, 5x, 3-4-5x")

def _validate_variables(vars: Dict[str, Any]) -> None:
    if not isinstance(vars, dict):
        raise ValueError("variables must be an object")
    # No strict schema for v0 -- but ensure names are strings
    for k in vars.keys():
        if not isinstance(k, str):
            raise ValueError("variables keys must be strings")

def _validate_template(tpl: Dict[str, Any]) -> None:
    # flat keys (e.g. "pass": "expr", "field": "expr") and nested maps like "place": {"6":"expr", ...}
    if not isinstance(tpl, dict):
        raise ValueError("mode.template must be an object")
    for k, v in tpl.items():
        if k in ("place", "buy", "lay", "come", "dont_come"):
            if not isinstance(v, dict):
                raise ValueError(f"template.{k} must be an object of number->expr")
            for num, expr in v.items():
                # keys may be strings of ints ("4","5","6","8","9","10")
                if not isinstance(num, str):
                    raise ValueError(f"template.{k} keys must be strings (box numbers), got {type(num).__name__}")
                if not isinstance(expr, (str, int, float)):
                    raise ValueError(f"template.{k}['{num}'] must be string/number expression")
        else:
            if not isinstance(v, (str, int, float)):
                raise ValueError(f"template.{k} must be string/number expression")

def _validate_modes(modes: Dict[str, Any]) -> None:
    if not isinstance(modes, dict) or not modes:
        raise ValueError("modes must be a non-empty object")
    for name, body in modes.items():
        if not isinstance(name, str) or not name:
            raise ValueError("mode names must be non-empty strings")
        if not isinstance(body, dict):
            raise ValueError(f"mode '{name}' must be an object")
        _require_keys(body, ("template",), f"modes['{name}']")
        _validate_template(body["template"])

def _validate_rule(rule: Dict[str, Any]) -> None:
    _require_keys(rule, ("on", "do"), "rule")
    if not isinstance(rule["on"], dict):
        raise ValueError("rule.on must be an object")
    ev = rule["on"].get("event")
    if ev not in ALLOWED_EVENTS:
        raise ValueError(f"rule.on.event must be one of {sorted(ALLOWED_EVENTS)}")
    # if bet_resolved, allow further keys
    if ev == "bet_resolved":
        # optional filters: bet, result, reason
        pass
    # optional "if": expression string
    if "if" in rule and not isinstance(rule["if"], str):
        raise ValueError("rule.if must be a string expression")
    # "do": list of action strings
    if not isinstance(rule["do"], list) or not rule["do"]:
        raise ValueError("rule.do must be a non-empty array of action strings")
    for a in rule["do"]:
        if not isinstance(a, str):
            raise ValueError("rule.do[] must be strings")

def _validate_rules(rules: Any) -> None:
    if not isinstance(rules, list):
        raise ValueError("rules must be an array")
    for r in rules:
        if not isinstance(r, dict):
            raise ValueError("each rule must be an object")
        _validate_rule(r)

def validate_spec(spec: Dict[str, Any]) -> None:
    """
    Validate a v0 Control spec.

    IMPORTANT: This function raises ValueError on invalid specs
    (the CLI depends on the exception to return a non-zero exit code).
    """
    if not isinstance(spec, dict):
        raise ValueError("spec must be a JSON object")

    _require_keys(spec, REQUIRED_TOP_LEVEL_KEYS, "spec")

    _validate_meta(spec["meta"])
    _validate_table(spec["table"])
    _validate_variables(spec["variables"])
    _validate_modes(spec["modes"])
    _validate_rules(spec["rules"])

    # Optional blocks
    if "telemetry" in spec and not isinstance(spec["telemetry"], dict):
        raise ValueError("telemetry must be an object if provided")