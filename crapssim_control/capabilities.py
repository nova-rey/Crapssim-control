from __future__ import annotations

# Engine-agnostic default “truthfulness” for vanilla CrapsSim:
SUPPORTED = {
    # Vanilla CrapsSim does not expose native Buy/Lay bet classes; these are emulated or unsupported.
    "buy_bet": False,
    "lay_bet": False,

    # ATS is present in vanilla (class names may vary, adapter resolves tolerantly).
    "ats_all_bet": True,
    "ats_small_bet": True,
    "ats_tall_bet": True,
}

CAPABILITIES = {
    "phase": 9,
    "capabilities_schema": "1.1",
    "verbs": {
        "line": ["line_bet", "set_odds", "take_odds", "remove_odds"],
        "place": ["place_bet", "buy_bet", "lay_bet", "take_down", "move_bet"],
        "props": ["any7_bet", "anycraps_bet", "yo_bet", "craps2_bet", "craps3_bet", "craps12_bet", "ce_bet", "hop_bet"],
        "bonus": ["ats_all_bet", "ats_small_bet", "ats_tall_bet"],
        "control": ["set_working", "clear_all", "cancel_bet"],
        "meta": ["start_session", "step_roll"]
    },
    "increments": {
        "place_6_8": 6,
        "place_4_5_9_10": 5,
        "odds_multiple": [1, 2, 3, 4, 5]
    },
    "supported": SUPPORTED
}


def get_capabilities() -> dict:
    return CAPABILITIES
