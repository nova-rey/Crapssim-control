# crapssim_control/actions.py
from __future__ import annotations

"""
Action Envelope schema (v1.0)

Every action emitted by CrapsSim-Control (from templates now, rules later)
must conform to this shape so downstream consumers (CSV exporter, UIs, tests)
can rely on a single contract.

Envelope (per action):
    {
      "source": "template" | "rule",                  # producer of the action
      "id": "template:<mode>" | "rule:<name-or-idx>", # stable identifier
      "action": "set" | "clear" | "press" | "reduce" | "switch_mode",
      "bet_type": "pass_line" | "place_6" | "odds_6_pass" | None,
      "amount": float | None,                          # None when not applicable
      "notes": str                                     # brief reason or context
    }

Conventions:
- IDs are namespaced ("template:Main", "rule:press_on_point", "rule:#2").
- Use amount=None when not meaningful; don't overload with 0.
- Additional optional fields may be added in future minor revisions (additive).
"""

from typing import Any, Optional, Dict

# TypedDict compatibility
try:
    from typing import TypedDict  # py>=3.8
except Exception:  # pragma: no cover
    from typing_extensions import TypedDict  # type: ignore

SCHEMA_VERSION: str = "1.0"

# ---- Allowed values -------------------------------------------------------------

SOURCE_TEMPLATE: str = "template"
SOURCE_RULE: str = "rule"
# Reserved for future:
# SOURCE_EVO: str = "evo"

ACTION_SET: str = "set"
ACTION_CLEAR: str = "clear"
ACTION_PRESS: str = "press"
ACTION_REDUCE: str = "reduce"
ACTION_SWITCH_MODE: str = "switch_mode"

ALLOWED_SOURCES = {SOURCE_TEMPLATE, SOURCE_RULE}
ALLOWED_ACTIONS = {
    ACTION_SET,
    ACTION_CLEAR,
    ACTION_PRESS,
    ACTION_REDUCE,
    ACTION_SWITCH_MODE,
}


class ActionEnvelope(TypedDict, total=False):
    """
    Strongly-typed view of an action for static tooling and tests.
    All keys are expected at runtime; some may be None depending on action type.
    """
    source: str
    id: str
    action: str
    bet_type: Optional[str]
    amount: Optional[float]
    notes: str


def make_action(
    action: str,
    bet_type: Optional[str] = None,
    amount: Optional[float] = None,
    *,
    source: str = SOURCE_TEMPLATE,
    id_: str = "template:Main",
    notes: str = "",
) -> ActionEnvelope:
    """
    Build a well-formed ActionEnvelope with consistent defaults.

    Parameters:
        action: One of ALLOWED_ACTIONS ("set", "clear", "press", "reduce", "switch_mode")
        bet_type: Canonical bet key (e.g., "pass_line", "place_6"), or None
        amount: Numeric amount for actions where it applies; None otherwise
        source: "template" or "rule" (reserve "evo" for later)
        id_: Stable identifier for the producer (e.g., "template:Main", "rule:press_on_point")
        notes: Brief free-form context (e.g., "auto-regress after 3rd roll")

    Returns:
        ActionEnvelope dict with all standard keys present.
    """
    # Lightweight guards (don’t raise; keep envelopes flowing)
    if source not in ALLOWED_SOURCES:
        source = SOURCE_TEMPLATE
    if action not in ALLOWED_ACTIONS:
        # Fall back to a no-op-ish shape but keep the original string
        # This avoids raising in hot paths; tests/exporter can validate separately.
        action = action  # keep as-is; exporter/tests may flag it

    # Normalize amount to float or None
    amt: Optional[float]
    if amount is None:
        amt = None
    else:
        try:
            amt = float(amount)
        except Exception:
            amt = None

    return ActionEnvelope(
        source=source,
        id=id_,
        action=action,
        bet_type=bet_type,
        amount=amt,
        notes=notes or "",
    )


__all__ = [
    "SCHEMA_VERSION",
    "ActionEnvelope",
    "make_action",
    "SOURCE_TEMPLATE",
    "SOURCE_RULE",
    "ACTION_SET",
    "ACTION_CLEAR",
    "ACTION_PRESS",
    "ACTION_REDUCE",
    "ACTION_SWITCH_MODE",
    "ALLOWED_SOURCES",
    "ALLOWED_ACTIONS",
]