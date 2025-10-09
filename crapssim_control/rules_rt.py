# crapssim_control/rules_rt.py
from __future__ import annotations

"""
rules_rt.py — Runtime Rules (Phase 2 stub)

Purpose
-------
Provide a stable interface for applying rule-based actions so the controller
can call into it *now*, while we keep the actual trigger logic for Phase 3.

Contract (stable)
-----------------
apply_rules(rules, state, event) -> list[ActionEnvelope-like dicts]

- Input:
    rules : list[dict] | None
        Strategy rules as defined in the spec (shape will be validated elsewhere).
    state : dict
        Current evaluation state (table cfg + user variables + controller snapshot).
    event : dict
        Current event context (e.g., {"type": "roll", ...}).

- Output (Phase 2):
    [] (no actions yet). This keeps behavior unchanged while letting the
    controller wire in the call and merge results.

Forward plan (Phase 3)
----------------------
- Parse rule "on" conditions (event type, predicates).
- Evaluate expressions with the safe evaluator (eval.py).
- Produce actions using `actions.make_action(...)` with source="rule" and
  id_="rule:<name-or-index>".
- Merge with template actions and pass through to CSV exporter.

Note
----
We intentionally avoid importing `actions.make_action` here in the stub so we
don’t pull extra dependencies into the minimal Phase 2 path. Phase 3 will add it.
"""

from typing import Any, Dict, List, Optional


def apply_rules(
    rules: Optional[List[Dict[str, Any]]],
    state: Dict[str, Any],
    event: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Phase 2 stub: accept spec-shaped inputs, return no actions.

    Parameters
    ----------
    rules : list[dict] | None
        The 'rules' array from the strategy spec. Ignored in the stub.
    state : dict
        Evaluator state (table + variables + controller snapshot). Unused here.
    event : dict
        Event context (e.g., {"type": "roll"}). Unused here.

    Returns
    -------
    list[dict]
        Always an empty list in Phase 2. Phase 3 will return Action Envelopes.
    """
    # Defensive shape checks (no-op but helpful for callers/test clarity)
    if rules is None:
        return []
    if not isinstance(rules, list):
        # Be permissive in Phase 2; return no actions rather than raising.
        return []

    # Placeholder: no rule evaluation in Phase 2.
    return []