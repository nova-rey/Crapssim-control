# crapssim_control/events.py
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple, Set

"""
events.py — Canonical Event Normalization (Phase 4 · Checkpoint 2)

Purpose
-------
Provide a single, authoritative definition of CrapsSim-Control event types and
their normalized payloads. This module converts raw engine/game-state snapshots
into a consistent event dictionary used throughout the controller, rules engine,
and CSV journaling.

Features
--------
✅ Stable event type constants for validation and docs.
✅ Uniform event schema for all events (even when fields are None).
✅ Helper `canonicalize_event()` that guarantees predictable keys.
✅ Backwards-compatible alias: 'event' == 'type'.
✅ Works with both dict-based and object-based game state inputs.
"""

# ---------------------------------------------------------------------------
# Canonical event names and numeric groups
# ---------------------------------------------------------------------------

COMEOUT = "comeout"
POINT_ESTABLISHED = "point_established"
POINT_MADE = "point_made"
ROLL = "roll"
SEVEN_OUT = "seven_out"

CANONICAL_EVENT_TYPES: Set[str] = {
    COMEOUT,
    POINT_ESTABLISHED,
    POINT_MADE,
    ROLL,
    SEVEN_OUT,
}

POINT_NUMS = {4, 5, 6, 8, 9, 10}
CRAPS_NUMS = {2, 3, 12}
NATURAL_NUMS = {7, 11}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _as_tuple3(x: Any) -> Tuple[int, int, int]:
    """Safely coerce dice-like inputs into (d1, d2, total)."""
    if isinstance(x, tuple) and len(x) >= 3:
        return int(x[0]), int(x[1]), int(x[2])
    try:
        return 0, 0, int(x)
    except Exception:
        return 0, 0, 0


def _normalize_state(s: Any) -> Dict[str, Any]:
    """
    Normalize various state inputs (dict or CrapsSim engine GameState) into a
    uniform dict of primitive flags and numbers.
    """
    if hasattr(s, "table"):
        t = getattr(s, "table", None)
        comeout = bool(getattr(t, "comeout", False))
        _, _, total = _as_tuple3(getattr(t, "dice", (0, 0, 0)))
        point_on = bool(getattr(t, "point_on", False))
        point_num = getattr(t, "point_number", None)
        just_est = bool(
            getattr(s, "just_established_point", False)
            or getattr(s, "just_est", False)
        )
        just_made = bool(
            getattr(s, "just_made_point", False)
            or getattr(s, "just_made", False)
        )
        return {
            "comeout": comeout,
            "total": int(total),
            "point_on": point_on,
            "point_num": point_num,
            "just_est": just_est,
            "just_made": just_made,
        }

    if isinstance(s, dict):
        return {
            "comeout": bool(s.get("comeout", False)),
            "total": int(s.get("total", 0)),
            "point_on": bool(s.get("point_on", False)),
            "point_num": s.get("point_num"),
            "just_est": bool(s.get("just_est", False)),
            "just_made": bool(s.get("just_made", False)),
        }

    # fallback (invalid input)
    return {
        "comeout": False,
        "total": 0,
        "point_on": False,
        "point_num": None,
        "just_est": False,
        "just_made": False,
    }


# ---------------------------------------------------------------------------
# Derivation logic
# ---------------------------------------------------------------------------

def derive_event(prev: Any, curr: Any) -> Dict[str, Any]:
    """
    Derive a semantic event from previous and current game-state snapshots.

    Returns a dict with canonical keys:
        type        : str   — canonical event type (see CANONICAL_EVENT_TYPES)
        event       : str   — alias of type (for backward compatibility)
        roll        : int   — current dice total
        point       : int|None — active point (if any)
        natural     : bool  — true for comeout naturals
        craps       : bool  — true for comeout craps
        on_comeout  : bool  — convenience flag
        point_on    : bool  — same as engine state
    """
    c = _normalize_state(curr)

    roll: int = int(c["total"])
    comeout: bool = bool(c["comeout"])
    point_on: bool = bool(c["point_on"])
    point_num: Optional[int] = c["point_num"]
    just_est: bool = bool(c["just_est"])
    just_made: bool = bool(c["just_made"])

    natural = False
    craps = False

    # Priority of semantic events:
    if just_est:
        evt = POINT_ESTABLISHED
    elif just_made:
        evt = POINT_MADE
    else:
        if comeout:
            if roll in NATURAL_NUMS:
                natural = True
                evt = COMEOUT
            elif roll in CRAPS_NUMS:
                craps = True
                evt = COMEOUT
            elif roll in POINT_NUMS:
                evt = POINT_ESTABLISHED  # defensive fallback
            else:
                evt = COMEOUT
        else:
            if point_on and point_num is not None and roll == point_num:
                evt = POINT_MADE
            elif roll == 7:
                evt = SEVEN_OUT
            else:
                evt = ROLL

    return canonicalize_event(
        {
            "type": evt,
            "event": evt,
            "roll": roll,
            "point": point_num if point_on else None,
            "natural": natural,
            "craps": craps,
            "on_comeout": comeout,
            "point_on": point_on,
        }
    )


# ---------------------------------------------------------------------------
# Canonicalization layer
# ---------------------------------------------------------------------------

def canonicalize_event(ev: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalize an arbitrary event dict (possibly partial) into a canonical
    structure expected by rules_rt and controller.

    Missing keys are inserted with defaults. Unknown extra keys are preserved.
    """
    if not ev or not isinstance(ev, dict):
        return {
            "type": COMEOUT,
            "event": COMEOUT,
            "roll": 0,
            "point": None,
            "natural": False,
            "craps": False,
            "on_comeout": True,
            "point_on": False,
        }

    t = ev.get("type") or ev.get("event") or COMEOUT
    if t not in CANONICAL_EVENT_TYPES:
        # downgrade to roll if unknown (rules validator will warn separately)
        t = ROLL

    return {
        "type": t,
        "event": t,  # maintain alias
        "roll": int(ev.get("roll", 0)),
        "point": ev.get("point"),
        "natural": bool(ev.get("natural", False)),
        "craps": bool(ev.get("craps", False)),
        "on_comeout": bool(ev.get("on_comeout", t == COMEOUT)),
        "point_on": bool(ev.get("point_on", bool(ev.get("point")))),
        # preserve any additional fields for advanced uses
        **{k: v for k, v in ev.items() if k not in {
            "type", "event", "roll", "point", "natural", "craps",
            "on_comeout", "point_on"
        }},
    }


__all__ = [
    "derive_event",
    "canonicalize_event",
    "COMEOUT",
    "POINT_ESTABLISHED",
    "POINT_MADE",
    "ROLL",
    "SEVEN_OUT",
    "CANONICAL_EVENT_TYPES",
]