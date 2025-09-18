# crapssim_control/spec_validate.py
"""
Batch 17 -- Spec Validation (lenient)

Public API:
- validate_spec(spec) -> (ok: bool, errors: list[str], warnings: list[str])
- assert_valid_spec(spec) -> None (raises SpecValidationError if not ok)

Design goals:
- Fail fast on *structural* problems (missing keys, wrong basic types).
- Be tolerant of content details (expressions, bet names, custom fields).
- Produce friendly, actionable messages for CI and humans.

No external dependencies required.
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple


class SpecValidationError(Exception):
    """Raised when a SPEC is structurally invalid."""
    def __init__(self, errors: List[str], warnings: List[str] | None = None):
        self.errors = errors
        self.warnings = warnings or []
        msg = "Spec validation failed:\n" + "\n".join(f"- {e}" for e in errors)
        if self.warnings:
            msg += "\n\nWarnings:\n" + "\n".join(f"- {w}" for w in self.warnings)
        super().__init__(msg)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _coerce_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def validate_spec(spec: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    """
    Validate a SPEC dict.

    Returns:
      (ok, errors, warnings)
    """
    errors: List[str] = []
    warnings: List[str] = []

    # Root type
    if not isinstance(spec, dict):
        return False, ["Top-level SPEC must be a dict/object."], []

    # Required top-level keys
    for k in ("table", "variables", "modes", "rules"):
        if k not in spec:
            errors.append(f"Missing required top-level key: '{k}'")

    # Early exit if critical keys missing
    if errors:
        return False, errors, warnings

    # table
    table = spec.get("table")
    if not isinstance(table, dict):
        errors.append("'table' must be an object.")
    else:
        if "bubble" not in table:
            errors.append("'table.bubble' is required (bool).")
        elif not isinstance(table["bubble"], bool):
            errors.append("'table.bubble' must be a boolean.")

        if "level" not in table:
            errors.append("'table.level' is required (number).")
        elif not _is_number(table["level"]):
            errors.append("'table.level' must be a number.")
        elif table["level"] <= 0:
            warnings.append("'table.level' is <= 0 -- is that intended?")

        # optional odds_policy as str (do not enforce enumeration here)
        if "odds_policy" in table and table["odds_policy"] is not None and not isinstance(table["odds_policy"], str):
            warnings.append("'table.odds_policy' should be a string or null.")

    # variables
    variables = spec.get("variables")
    if not isinstance(variables, dict):
        errors.append("'variables' must be an object.")
    else:
        # Gentle hint if units are missing (many templates reference it)
        if "units" not in variables:
            warnings.append("No 'variables.units' defined -- templates often reference 'units'.")

    # modes + templates
    modes = spec.get("modes")
    if not isinstance(modes, dict) or not modes:
        errors.append("'modes' must be a non-empty object.")
    else:
        for name, mode in modes.items():
            if not isinstance(mode, dict):
                errors.append(f"Mode '{name}' must be an object.")
                continue
            tmpl = mode.get("template", {})
            if tmpl is None:
                tmpl = {}
            if not isinstance(tmpl, dict):
                errors.append(f"Mode '{name}.template' must be an object mapping bet->amount/expr.")
                continue
            for bet_key, val in tmpl.items():
                # Accept either number/string OR object with 'amount'
                if isinstance(val, (str, int, float)):
                    pass  # fine
                elif isinstance(val, dict):
                    if "amount" not in val:
                        errors.append(f"Mode '{name}.template.{bet_key}' object must contain 'amount'.")
                    else:
                        amt = val["amount"]
                        if not isinstance(amt, (str, int, float)):
                            errors.append(
                                f"Mode '{name}.template.{bet_key}.amount' must be a number or string expression."
                            )
                else:
                    errors.append(
                        f"Mode '{name}.template.{bet_key}' must be number/string or object with 'amount'."
                    )

    # rules
    rules = spec.get("rules")
    if not isinstance(rules, list):
        errors.append("'rules' must be an array/list.")
    else:
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                errors.append(f"Rule[{i}] must be an object.")
                continue
            if "on" not in rule:
                errors.append(f"Rule[{i}] is missing 'on'.")
            if "do" not in rule:
                errors.append(f"Rule[{i}] is missing 'do'.")
            on = rule.get("on", {})
            if not isinstance(on, dict):
                errors.append(f"Rule[{i}].on must be an object.")
            do = rule.get("do", [])
            if not isinstance(do, list) or not all(isinstance(s, str) for s in do):
                errors.append(f"Rule[{i}].do must be a list of strings.")
            # Friendly nudge: common keys that make matching predictable
            if isinstance(on, dict):
                present = set(on.keys())
                common = {"event", "bet", "result"}
                if not present & common:
                    warnings.append(
                        f"Rule[{i}].on has no common match keys (event/bet/result); "
                        "ensure your runner knows how to match it."
                    )

    return (len(errors) == 0), errors, warnings


def assert_valid_spec(spec: Dict[str, Any]) -> None:
    """Raise SpecValidationError if the spec is invalid."""
    ok, errors, warnings = validate_spec(spec)
    if not ok:
        raise SpecValidationError(errors, warnings)