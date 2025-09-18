# crapssim_control/spec_validation.py
"""
Batch 17 -- Spec validation (dependency-free).

Purpose:
- Validate strategy specs early (before running).
- Provide clear, human-friendly error messages.
- Keep it light: no external jsonschema dependency.

Public API:
- validate_spec(spec) -> List[str]        # returns a list of error strings (empty if valid)
- assert_valid_spec(spec) -> None         # raises SpecValidationError if invalid
- is_valid_spec(spec) -> bool             # convenience

This validator is intentionally permissive on optional sections,
but strict on shape and types that our runtime expects.
"""

from typing import Any, Dict, List, Tuple, Optional


class SpecValidationError(Exception):
    """Raised when a spec fails validation."""
    def __init__(self, errors: List[str]):
        msg = "Spec validation failed:\n  - " + "\n  - ".join(errors)
        super().__init__(msg)
        self.errors = errors


# ------------------------------
# Helpers
# ------------------------------

def _type_name(x: Any) -> str:
    return type(x).__name__


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _is_bool(x: Any) -> bool:
    return isinstance(x, bool)


def _is_str(x: Any) -> bool:
    return isinstance(x, str)


def _optional_bool(obj: Dict[str, Any], key: str, path: str, errors: List[str]) -> Optional[bool]:
    if key not in obj:
        return None
    v = obj[key]
    if not _is_bool(v):
        errors.append(f"{path}.{key} must be boolean, got { _type_name(v) }")
        return None
    return v


def _optional_number(obj: Dict[str, Any], key: str, path: str, errors: List[str]) -> Optional[float]:
    if key not in obj:
        return None
    v = obj[key]
    if not _is_number(v):
        errors.append(f"{path}.{key} must be a number, got { _type_name(v) }")
        return None
    return float(v)


def _require_dict(obj: Any, path: str, errors: List[str]) -> Dict[str, Any]:
    if not isinstance(obj, dict):
        errors.append(f"{path} must be an object/dict, got { _type_name(obj) }")
        return {}
    return obj


def _require_list(obj: Any, path: str, errors: List[str]) -> List[Any]:
    if not isinstance(obj, list):
        errors.append(f"{path} must be an array/list, got { _type_name(obj) }")
        return []
    return obj


# ------------------------------
# Section validators
# ------------------------------

def _validate_meta(meta: Any, errors: List[str]) -> None:
    if meta is None:
        return
    meta = _require_dict(meta, "meta", errors)
    # optional: name (str), version (int/number)
    if "name" in meta and not _is_str(meta["name"]):
        errors.append(f"meta.name must be a string, got { _type_name(meta['name']) }")
    if "version" in meta and not _is_number(meta["version"]):
        errors.append(f"meta.version must be a number, got { _type_name(meta['version']) }")


def _validate_table(table: Any, errors: List[str]) -> None:
    if table is None:
        return
    table = _require_dict(table, "table", errors)
    # optional keys: bubble (bool), level (number), odds_policy (str)
    _optional_bool(table, "bubble", "table", errors)
    _optional_number(table, "level", "table", errors)
    if "odds_policy" in table and not _is_str(table["odds_policy"]):
        errors.append(f"table.odds_policy must be a string, got { _type_name(table['odds_policy']) }")


def _validate_variables(variables: Any, errors: List[str]) -> None:
    if variables is None:
        return
    variables = _require_dict(variables, "variables", errors)
    # all variable values should be primitives (str/number/bool)
    for k, v in variables.items():
        if not (_is_str(v) or _is_number(v) or _is_bool(v)):
            errors.append(f"variables['{k}'] must be string/number/bool, got { _type_name(v) }")


def _validate_template_dict(tmpl: Any, mode_name: str, errors: List[str], path: str) -> None:
    """
    Template is a mapping of bet_type -> amount/expression
    amount/expression can be number or string (expression).
    We allow nested dict like {'amount': 10} (already normalized elsewhere),
    but we strongly prefer number or string here in raw specs.
    """
    tmpl = _require_dict(tmpl, path, errors)
    for bet_type, val in tmpl.items():
        if _is_number(val) or _is_str(val):
            continue
        # Allow nested {"amount": number or string} for forward-compat
        if isinstance(val, dict):
            if "amount" not in val:
                errors.append(f"{path}['{bet_type}'] must be a number/string or an object with 'amount'")
            else:
                amt = val["amount"]
                if not (_is_number(amt) or _is_str(amt)):
                    errors.append(f"{path}['{bet_type}'].amount must be number or string, got { _type_name(amt) }")
        else:
            errors.append(f"{path}['{bet_type}'] must be number/string, got { _type_name(val) }")


def _validate_modes(modes: Any, errors: List[str]) -> None:
    modes = _require_dict(modes, "modes", errors)
    if not modes:
        errors.append("modes must define at least one mode (e.g., 'Main').")
        return
    for name, cfg in modes.items():
        if not isinstance(cfg, dict):
            errors.append(f"modes['{name}'] must be an object/dict, got { _type_name(cfg) }")
            continue
        # Expect a 'template' dict (runtime templates are allowed elsewhere; here we validate simple dicts)
        if "template" not in cfg:
            errors.append(f"modes['{name}'] is missing required key 'template'")
            continue
        _validate_template_dict(cfg["template"], name, errors, f"modes['{name}'].template")


def _validate_rule_on(on: Any, idx: int, errors: List[str]) -> None:
    on = _require_dict(on, f"rules[{idx}].on", errors)
    # required: event (str)
    event = on.get("event")
    if not _is_str(event):
        errors.append(f"rules[{idx}].on.event must be a string, got { _type_name(event) }")
    # optional filter fields; if present, must be strings or numbers
    for opt in ("bet", "result", "phase"):
        if opt in on and not _is_str(on[opt]):
            errors.append(f"rules[{idx}].on.{opt} must be a string, got { _type_name(on[opt]) }")
    if "point" in on and not _is_number(on["point"]):
        errors.append(f"rules[{idx}].on.point must be a number, got { _type_name(on['point']) }")


def _validate_rule_do(do: Any, idx: int, errors: List[str]) -> None:
    do = _require_list(do, f"rules[{idx}].do", errors)
    if not do:
        errors.append(f"rules[{idx}].do must contain at least one action string")
        return
    for j, action in enumerate(do):
        if not _is_str(action):
            errors.append(f"rules[{idx}].do[{j}] must be a string (expression like \"apply_template('Main')\"), got { _type_name(action) }")


def _validate_rules(rules: Any, errors: List[str]) -> None:
    rules = _require_list(rules, "rules", errors)
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"rules[{i}] must be an object/dict, got { _type_name(rule) }")
            continue
        if "on" not in rule:
            errors.append(f"rules[{i}] is missing required key 'on'")
        else:
            _validate_rule_on(rule["on"], i, errors)
        if "do" not in rule:
            errors.append(f"rules[{i}] is missing required key 'do'")
        else:
            _validate_rule_do(rule["do"], i, errors)


# ------------------------------
# Public API
# ------------------------------

def validate_spec(spec: Any) -> List[str]:
    """
    Validate a strategy spec and return a list of error messages.
    Empty list => valid.
    """
    errors: List[str] = []
    if not isinstance(spec, dict):
        return ["Spec root must be an object/dict"]

    # meta (optional)
    _validate_meta(spec.get("meta"), errors)

    # table (optional but common)
    _validate_table(spec.get("table"), errors)

    # variables (optional but common)
    _validate_variables(spec.get("variables"), errors)

    # modes (required)
    modes = spec.get("modes")
    if modes is None:
        errors.append("Missing required section: 'modes'")
    else:
        _validate_modes(modes, errors)

    # rules (required; may be empty list if no automation)
    if "rules" not in spec:
        errors.append("Missing required section: 'rules'")
    else:
        _validate_rules(spec.get("rules"), errors)

    return errors


def assert_valid_spec(spec: Any) -> None:
    errs = validate_spec(spec)
    if errs:
        raise SpecValidationError(errs)


def is_valid_spec(spec: Any) -> bool:
    return not validate_spec(spec)


# -------------- CLI (optional) --------------

def _main_cli() -> int:
    import json
    import sys
    import pathlib

    if len(sys.argv) != 2:
        print("Usage: python -m crapssim_control.spec_validation <path-to-spec.json>")
        return 2

    path = pathlib.Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        return 2

    try:
        spec = json.loads(path.read_text())
    except Exception as e:
        print(f"Failed to parse JSON: {e}")
        return 2

    errs = validate_spec(spec)
    if errs:
        print("Invalid spec:")
        for e in errs:
            print(f"  - {e}")
        return 1

    print("Spec is valid ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main_cli())