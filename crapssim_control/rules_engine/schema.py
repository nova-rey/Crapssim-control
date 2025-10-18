"""
Defines JSON-serializable schema for deterministic rule evaluation.
Used by evaluator.py to validate rule sets.
"""

from typing import Any, Dict, List

RULE_FIELDS = {
    "id": str,
    "when": str,
    "scope": str,
    "cooldown": (str, int, type(None)),
    "guard": (str, type(None)),
    "action": str,
    "enabled": bool,
}

def validate_rule(rule: Dict[str, Any]) -> List[str]:
    """Validate keys and types for a single rule. Returns list of error strings."""
    errors = []
    for key, val_type in RULE_FIELDS.items():
        if key not in rule:
            errors.append(f"Missing key: {key}")
            continue
        if not isinstance(rule[key], val_type):
            errors.append(f"Invalid type for {key}: {type(rule[key])}")
    return errors

def validate_ruleset(rules: List[Dict[str, Any]]) -> List[str]:
    errors = []
    ids = set()
    for rule in rules:
        errs = validate_rule(rule)
        if rule.get("id") in ids:
            errs.append(f"Duplicate rule id: {rule['id']}")
        ids.add(rule.get("id"))
        errors.extend([f"{rule.get('id','unknown')}: {e}" for e in errs])
    return errors
