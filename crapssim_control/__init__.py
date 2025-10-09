# crapssim_control/__init__.py
"""
CrapsSim Control — runtime templates, rule engine (MVP), controller, and CSV tooling.
"""

from .controller import ControlStrategy
from .templates_rt import render_template, diff_bets
from .rules_rt import apply_rules
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

# Bump for Phase 3 CSV + envelopes work
__version__ = "0.19.0"

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

    # Package version
    "__version__",
]