# crapssim_control/spec_validation.py
"""
Thin compatibility layer so tests can import:
  - validate_spec(spec) -> List[str]  (empty list means valid)
  - is_valid_spec(spec) -> bool
  - assert_valid_spec(spec) -> None or raises SpecValidationError(errors=list[str])
  - SpecValidationError

Internally we delegate to spec_validate.validate_spec(...) which returns a tuple:
    (ok: bool, errors: List[str], warnings: List[str])
This adapter normalizes that to the interface & wording expected by tests.
"""

from typing import Any, Dict, List, Tuple

# Import the real implementation
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

    # Add friendly hint if modes missing or empty (tests look for 'define at least one mode')
    modes = spec.get("modes", None)
    if modes is None or (isinstance(modes, dict) and len(modes) == 0):
        # Only add if not already present
        hint = "You must define at least one mode."
        if not any("define at least one mode" in s for s in out):
            out.append(hint)

    return out


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    """
    Validate the spec and return a LIST of error strings (empty list means valid).
    (This differs from the internal function, which returns a tuple.)
    """
    ok, errors, _warnings = _validate_tuple(spec)  # type: ignore[call-arg]
    # When ok is True, we should return [] regardless of warnings.
    if ok:
        return []
    # Normalize wording for tests
    return _normalize_messages(list(errors or []), spec)


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