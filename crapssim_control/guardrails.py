from __future__ import annotations
from typing import Any, Dict, List

Intent = Dict[str, Any]

def apply_guardrails(spec: Dict[str, Any], vs: Any, intents: List[Intent]) -> List[Intent]:
    """
    No-op scaffolding for conservative guardrails (table max, bankroll % caps, etc.).
    Batch 1 safety: return intents unchanged unless explicitly enabled later.
    """
    # Future (flagged) logic will go here.
    return intents