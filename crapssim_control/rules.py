# crapssim_control/rules.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .controller import ControlStrategy


def run_rules_for_event(
    spec: Dict[str, Any],
    ctrl_state: Any,
    event: Dict[str, Any],
    current_bets: Dict[str, Dict] | None = None,
    table_cfg: Dict[str, Any] | None = None,
) -> List[Tuple]:
    """
    Helper used by tests to run the controller and convert actions into
    simple tuples: (bet, number, action, amount)
    """
    cs = ControlStrategy(spec, ctrl_state, table_cfg=table_cfg or spec.get("table") or {})
    plan = cs.handle_event(event, current_bets or {})

    intents: List[Tuple] = []
    for a in plan:
        bet = a.get("bet")
        number = a.get("number")
        action = a.get("action")
        amount = a.get("amount")
        intents.append((bet, number, action, amount))
    return intents