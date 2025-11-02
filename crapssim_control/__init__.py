# crapssim_control/__init__.py
"""
CrapsSim Control — runtime templates, rule engine, controller, and CSV/report/export tooling.
Now includes P5C5 bundle export helpers.
"""

from .controller import ControlStrategy
from .templates import render_template, diff_bets
from .rules_engine import apply_rules
from .actions import (
    make_action,
    ActionEnvelope,
    SCHEMA_VERSION as ACTION_SCHEMA_VERSION,
    ACTION_SET,
    ACTION_CLEAR,
    ACTION_PRESS,
    ACTION_REDUCE,
    ACTION_SWITCH_MODE,
    SOURCE_TEMPLATE,
    SOURCE_RULE,
)
from .csv_journal import CSVJournal
from .csv_summary import summarize_journal, write_summary_csv
from .bundles import export_bundle, import_evo_bundle
from .bundles import ExportEmptyError, BundleReadError, SchemaMismatchError

# Phase 5 Cycle 5 — includes report/export integration
__version__ = "1.0.1-lts"

# HTTP API metadata
API_VERSION = "v1"
API_DEPRECATION_NOTICE = "Legacy /api routes are deprecated; use /api/v1"

__all__ = [
    # Core controller
    "ControlStrategy",
    # Runtime templates
    "render_template",
    "diff_bets",
    # Rules (MVP)
    "apply_rules",
    # Action envelopes
    "make_action",
    "ActionEnvelope",
    "ACTION_SCHEMA_VERSION",
    "ACTION_SET",
    "ACTION_CLEAR",
    "ACTION_PRESS",
    "ACTION_REDUCE",
    "ACTION_SWITCH_MODE",
    "SOURCE_TEMPLATE",
    "SOURCE_RULE",
    # CSV utilities
    "CSVJournal",
    "summarize_journal",
    "write_summary_csv",
    "export_bundle",
    "import_evo_bundle",
    "ExportEmptyError",
    "BundleReadError",
    "SchemaMismatchError",
    # Package version
    "__version__",
    "API_VERSION",
    "API_DEPRECATION_NOTICE",
]
