# crapssim_control/actions.py
from __future__ import annotations

"""
Action Envelope schema (v1.1 · P4C4)

Every action emitted by CrapsSim-Control (from templates and rules)
must conform to this shape so downstream consumers (CSV exporter, UIs, tests)
can rely on a single contract.

Envelope (per action):
    {
      "source": "template" | "rule",                  # producer of the action
      "id": "template:<mode>" | "rule:<name-or-idx>", # stable identifier
      "action": "set" | "clear" | "press" | "reduce" | "switch_mode" | "setvar",
      "bet_type": "pass_line" | "place_6" | "odds_6_pass" | None,
      "amount": float | None,                         # None when not applicable
      "notes": str,                                   # brief reason or context
      # [P4C3] optional:
      # "seq": int,                                   # per-event sequence, annotated by controller
      # [P4C4] optional (for setvar):
      # "var": str,                                   # variable name to set (e.g., "win_streak")
      # "value": Any                                  # expression or literal to apply
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

SCHEMA_VERSION: str = "1.1"

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
ACTION_SETVAR: str = "setvar"  # P4C4

ALLOWED_SOURCES = {SOURCE_TEMPLATE, SOURCE_RULE}
ALLOWED_ACTIONS = {
    ACTION_SET,
    ACTION_CLEAR,
    ACTION_PRESS,
    ACTION_REDUCE,
    ACTION_SWITCH_MODE,
    ACTION_SETVAR,  # allow controller/rules to normalize this
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
    seq: int  # optional, added by controller during journaling
    # P4C4 (setvar)
    var: str
    value: Any


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
        action: One of ALLOWED_ACTIONS ("set", "clear", "press", "reduce", "switch_mode", "setvar")
        bet_type: Canonical bet key (e.g., "pass_line", "place_6"), or None
        amount: Numeric amount for actions where it applies; None otherwise
        source: "template" or "rule" (reserve "evo" for later)
        id_: Stable identifier for the producer (e.g., "template:Main", "rule:press_on_point")
        notes: Brief free-form context (e.g., "auto-regress after 3rd roll")

    Returns:
        ActionEnvelope dict with all standard keys present.
    """
    # Lightweight guards (don’t raise; keep envelopes flowing)
    src = (source or "").lower()
    if src not in ALLOWED_SOURCES:
        src = SOURCE_TEMPLATE

    act = (action or "").lower()
    if act not in ALLOWED_ACTIONS:
        # Keep as-is to allow validators to flag; don't crash hot paths.
        act = action

    # Normalize amount to float or None (bet actions only; ignored by setvar/switch_mode)
    amt: Optional[float]
    if amount is None:
        amt = None
    else:
        try:
            amt = float(amount)
        except Exception:
            amt = None

    bt = str(bet_type) if isinstance(bet_type, str) and bet_type else None

    return ActionEnvelope(
        source=src,
        id=id_ or "",
        action=act,
        bet_type=bt,
        amount=amt,
        notes=str(notes or ""),
    )


# ---- P4C3 helpers ---------------------------------------------------------------

def normalize_action(env: Dict[str, Any]) -> ActionEnvelope:
    """
    Normalize an arbitrary action-like dict to a compliant ActionEnvelope.
    - Lowercases 'source' and 'action' (when applicable).
    - Coerces 'amount' to float or None.
    - Coerces 'bet_type' to str or None.
    - Ensures required keys exist with safe defaults.
    - Preserves optional 'var' and 'value' for setvar if present.
    Does not raise; best-effort normalization.
    """
    source = (env.get("source") or SOURCE_TEMPLATE)
    action = (env.get("action") or "")
    bet_type = env.get("bet_type")
    amount = env.get("amount")
    notes = env.get("notes") or ""
    id_ = env.get("id") or "template:Main"

    out = make_action(
        action=action,
        bet_type=str(bet_type) if isinstance(bet_type, str) and bet_type else None,
        amount=amount if isinstance(amount, (int, float, str)) else None,
        source=str(source).lower(),
        id_=str(id_),
        notes=str(notes),
    )

    # Preserve setvar extras if present
    if (str(action).lower() == ACTION_SETVAR):
        var = env.get("var")
        if isinstance(var, str) and var.strip():
            out["var"] = var.strip()
        if "value" in env:
            out["value"] = env.get("value")

    return out


def is_bet_action(env: Dict[str, Any]) -> bool:
    """
    True if the action mutates or clears a specific bet.
    """
    a = (env.get("action") or "").lower()
    if a not in (ACTION_SET, ACTION_PRESS, ACTION_REDUCE, ACTION_CLEAR):
        return False
    bt = env.get("bet_type")
    return isinstance(bt, str) and bool(bt)


__all__ = [
    "SCHEMA_VERSION",
    "ActionEnvelope",
    "make_action",
    "normalize_action",
    "is_bet_action",
    "SOURCE_TEMPLATE",
    "SOURCE_RULE",
    "ACTION_SET",
    "ACTION_CLEAR",
    "ACTION_PRESS",
    "ACTION_REDUCE",
    "ACTION_SWITCH_MODE",
    "ACTION_SETVAR",
    "ALLOWED_SOURCES",
    "ALLOWED_ACTIONS",
]