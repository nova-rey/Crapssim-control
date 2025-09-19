"""
Crapssim Control - strategy specs, rule engine, and CLI wrapper.
"""

from .controller import ControlStrategy
from .materialize import apply_intents
from .rules import run_rules_for_event
from .templates import render_template
from .spec_validation import (
    validate_spec, assert_valid_spec, is_valid_spec, SpecValidationError
)
from .tracker import Tracker
from .bet_types import normalize_bet_type

# Keep version here so CLI can import it safely
__version__ = "0.18.0"

__all__ = [
    "ControlStrategy",
    "apply_intents",
    "run_rules_for_event",
    "render_template",
    "validate_spec",
    "assert_valid_spec",
    "is_valid_spec",
    "SpecValidationError",
    "Tracker",
    "normalize_bet_type",
    "__version__",
]