# crapssim_control/spec_validation.py
"""
Compatibility layer so tests can import:
  - validate_spec(spec) -> List[str]  (empty list means valid)
  - is_valid_spec(spec) -> bool
  - assert_valid_spec(spec) -> None or raises SpecValidationError(errors=list[str])
  - SpecValidationError

We delegate to spec_validate.validate_spec(...) which returns (ok, errors, warnings),
then normalize wording and add a few explicit checks to match tests' expected strings.
"""

from typing import Any, Dict, List, Tuple

# Real implementation (tuple-returning)
from .spec_validate import validate_spec as _validate_tuple  # (ok, errors, warnings)


class SpecValidationError(Exception):
    """Raised by assert_valid_spec when the strategy spec is invalid."""
    def __init__(self, errors: List[str]) -> None:
        self.errors = list(errors) if errors else []
        msg = "Spec validation failed:\n" + "\n".join(self.errors) if self.errors else "Spec validation failed."
        super().__init__(msg)


def _normalize_messages(errors: List[str], spec: Dict[str, Any]) -> List[str]:
    """
    Adjust message wording to match tests' expectations.
    - Replace 'top-level key' with 'section'
    - If modes missing or empty, add a friendly hint containing 'define at least one mode'
    """
    out: List[str] = []
    for e in errors:
        e2 = e.replace("top-level key", "section")
        out.append(e2)

    # Friendly hint if modes missing or empty (tests look for 'define at least one mode')
    modes = spec.get("modes", None)
    if modes is None or (isinstance(modes, dict) and len(modes) == 0):
        hint = "You must define at least one mode."
        if not any("define at least one mode" in s for s in out):
            out.append(hint)

    return out


def _post_checks(spec: Dict[str, Any], messages: List[str]) -> List[str]:
    """
    Add/standardize a few messages the tests assert on explicitly, in case the
    underlying validator is looser or phrases them differently.
    """
    errs = list(messages)

    # A) Each mode must have a 'template'
    modes = spec.get("modes")
    if isinstance(modes, dict):
        for name, mode in modes.items():
            if not isinstance(mode, dict) or "template" not in mode:
                msg = f"modes['{name}'] is missing required key 'template'"
                if msg not in errs:
                    errs.append(msg)

    # B) Template value shapes: allow number/string or {"amount": <num>}; otherwise error string must include phrase
    if isinstance(modes, dict):
        for mode in modes.values():
            tmpl = mode.get("template") if isinstance(mode, dict) else None
            if isinstance(tmpl, dict):
                for bet_key, val in tmpl.items():
                    # allow scalar (int/float/str)
                    if isinstance(val, (int, float, str)):
                        continue
                    # allow dict with 'amount'
                    if isinstance(val, dict):
                        if "amount" in val:
                            continue
                        # build message with required phrase; tests check substring only
                        phrase = "must be a number/string or an object with 'amount'"
                        # include the bet key to be helpful
                        msg = f"template['{bet_key}'] {phrase}"
                        if not any(phrase in e for e in errs):
                            errs.append(msg)
                    else:
                        phrase = "must be a number/string or an object with 'amount'"
                        msg = f"template['{bet_key}'] {phrase}"
                        if not any(phrase in e for e in errs):
                            errs.append(msg)

    # C) Rules: on.event must be a string
    rules = spec.get("rules")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            on = rule.get("on", {})
            if isinstance(on, dict) and "event" in on and not isinstance(on.get("event"), str):
                msg = "on.event must be a string"
                if msg not in errs:
                    errs.append(msg)

    return errs


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    """
    Validate the spec and return a LIST of error strings (empty list means valid).
    We run the underlying tuple validator and then apply normalizations and post-checks.
    """
    ok, errors, _warnings = _validate_tuple(spec)  # type: ignore[call-arg]
    normed = _normalize_messages(list(errors or []), spec)
    # Run post-checks even if ok==True, so we can add stricter messages the tests expect.
    final_errs = _post_checks(spec, normed)

    # If the underlying validator said ok and we didn't add any new errors, return [].
    if ok and not final_errs:
        return []
    return final_errs


def is_valid_spec(spec: Dict[str, Any]) -> bool:
    """True when the spec passes validation (i.e., validate_spec(...) returns [])."""
    return len(validate_spec(spec)) == 0


def assert_valid_spec(spec: Dict[str, Any]) -> None:
    """
    Raise SpecValidationError with .errors (list[str]) if validation fails.
    Otherwise return None.
    """
    errors = validate_spec(spec)
    if errors:
        raise SpecValidationError(errors)


__all__ = [
    "validate_spec",
    "assert_valid_spec",
    "is_valid_spec",
    "SpecValidationError",
]