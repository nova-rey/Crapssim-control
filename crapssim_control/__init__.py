# crapssim_control/__init__.py
"""
Public package API.

Exports the core classes/functions that tests and users import from
`crapssim_control` directly.
"""

# Core strategy + engine adapter
from .controller import ControlStrategy
from .engine_adapter import EngineAdapter

# Template rendering helpers (used in some tests/spec tooling)
from .templates import render_template, render_runtime_template

# Safe evaluation utilities (tests import/expect these)
from .eval import (
    evaluate,
    eval_num,
    eval_bool,
    EvalError,
)

# Spec validation (Batch 17)
from .spec_validate import (
    validate_spec,
    assert_valid_spec,
    SpecValidationError,
)

__all__ = [
    # Core
    "ControlStrategy",
    "EngineAdapter",
    # Templates
    "render_template",
    "render_runtime_template",
    # Eval
    "evaluate",
    "eval_num",
    "eval_bool",
    "EvalError",
    # Spec validation
    "validate_spec",
    "assert_valid_spec",
    "SpecValidationError",
]