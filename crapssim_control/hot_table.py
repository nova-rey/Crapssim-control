from __future__ import annotations
from typing import Any, Dict, List

# Types are intentionally loose to avoid leaking into public API
Intent = Dict[str, Any]


def scale_bets_if_hot(spec: Dict[str, Any], vs: Any, intents: List[Intent]) -> List[Intent]:
    """
    No-op scaffolding for 'hot table' scaling.
    Batch 1 safety: always return intents unchanged unless explicitly enabled in a future wiring step.
    We keep this function pure and side-effect free.
    """
    # Future (flagged) logic will go here.
    return intents
