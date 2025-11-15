from __future__ import annotations
from typing import Iterable, Tuple, List, Dict, Any


def run_parity_test(
    inprocess_engine,
    http_engine,
    dice_stream: Iterable[Tuple[int, int]],
    steps: int,
) -> List[Dict[str, Any]]:
    """
    Run both engines through the same sequence of forced dice rolls and return
    a list of step-by-step comparison dictionaries.

    The harness does not assert; callers handle interpretation.
    """
    results = []

    for i, dice in enumerate(dice_stream):
        if i >= steps:
            break

        s1 = inprocess_engine.step_roll(dice=dice)
        s2 = http_engine.step_roll(dice=dice)

        results.append(
            {
                "index": i,
                "dice": dice,
                "inprocess": s1,
                "http_api": s2,
            }
        )

    return results
