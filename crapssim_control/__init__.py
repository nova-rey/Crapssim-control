# crapssim_control/__init__.py
"""
Public package API.

Exports the core classes/functions that tests and users import from
`crapssim_control` directly.
"""

# Core strategy + engine adapter
from .controller import ControlStrategy
from .engine_adapter import EngineAdapter

# Template rendering helper (runtime rendering is internal to controller/rules)
from .templates import render_template

# Safe evaluation utilities
from .eval import (
    evaluate,
    eval_num,
    eval_bool,
    EvalError,
)

# Spec validation (tests import via crapssim_control.spec_validation, but we
# also surface the API at the package root for convenience)
from .spec_validation import (
    validate_spec,
    assert_valid_spec,
    is_valid_spec,
    SpecValidationError,
)

__all__ = [
    # Core
    "ControlStrategy",
    "EngineAdapter",
    # Templates
    "render_template",
    # Eval
    "evaluate",
    "eval_num",
    "eval_bool",
    "EvalError",
    # Spec validation
    "validate_spec",
    "assert_valid_spec",
    "is_valid_spec",
    "SpecValidationError",
]