"""Capability descriptors exposed for manifest and introspection."""

from __future__ import annotations

from typing import Any, Dict


CAPABILITIES: Dict[str, Any] = {
    "phase": 9,
    "capabilities_schema": "1.0",
    "verbs": {
        "line": ["line_bet", "take_odds", "set_odds", "remove_odds"],
        "place": ["place_bet", "buy_bet", "lay_bet", "take_down", "move_bet"],
        "props": [
            "any7_bet",
            "anycraps_bet",
            "yo_bet",
            "craps2_bet",
            "craps3_bet",
            "craps12_bet",
            "ce_bet",
            "hop_bet",
        ],
        "bonus": ["ats_all_bet", "ats_small_bet", "ats_tall_bet"],
        "meta": ["set_working", "clear_all"],
    },
    "increments": {
        "place_6_8": 6,
        "place_5_9_4_10": 5,
        "odds_multiple": [1, 2, 3, 4, 5],
    },
    "supported": {
        "ats_all": True,
        "ats_small": True,
        "ats_tall": True,
        "fire_bet": False,
    },
}


def get_capabilities() -> Dict[str, Any]:
    """Return the static capability map for CSC integrations."""

    return CAPABILITIES
