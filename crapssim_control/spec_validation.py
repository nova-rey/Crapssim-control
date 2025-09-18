# crapssim_control/spec_validation.py
"""
Spec validation shim.

Tests import from `crapssim_control.spec_validation`. This module provides the
expected API and delegates to the internal implementation.
"""

from .spec_validate import (
    validate_spec,
    assert_valid_spec,
    SpecValidationError,
)

def is_valid_spec(spec) -> bool:
    """Return True/False only, based on validate_spec result."""
    ok, _ = validate_spec(spec)
    return bool(ok)

__all__ = [
    "validate_spec",
    "assert_valid_spec",
    "is_valid_spec",
    "SpecValidationError",
]