# crapssim_control/events_std.py
"""
events_std.py — Canonical Event Stream (Phase 4 · Checkpoint 2)

Purpose
-------
Provide a small, engine-agnostic event derivation state machine that produces
a **canonicalized, schema-stable** stream of event dicts for the controller and
rule engine.

This file now integrates tightly with :mod:`crapssim_control.events` so that all
event payloads share the same canonical keys (`type`, `event`, `roll`, `point`,
`on_comeout`, etc.).

Design goals
------------
✅ Deterministic event ordering (no duplicates, no ambiguity)  
✅ Uniform payloads regardless of engine adapter  
✅ Safe for CSV, rule evaluation, and compiler consumption  
✅ Backwards-compatible with older tests and controller logic
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List, Optional, Tuple
from collections import deque

from .events import (
    canonicalize_event,
    COMEOUT,
    POINT_ESTABLISHED,
    ROLL,
    SEVEN_OUT,
    CANONICAL_EVENT_TYPES,
)

_POINT_NUMBERS = {4, 5, 6, 8, 9, 10}


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

@dataclass
class _State:
    shooter_id: Optional[int] = None
    point: Optional[int] = None
    on_comeout: bool = True
    roll_index: int = 0


# ---------------------------------------------------------------------------
# Event Stream
# ---------------------------------------------------------------------------

class EventStream:
    """
    Minimal state machine that derives canonical control events from simple inputs.

    Call sequence:
      • new_shooter(shooter_id)
      • roll(total, dice=None)
      • resolve(bet_type, result, payout=None, reason=None)
      • flush()  → yields canonicalized event dicts
    """

    def __init__(self) -> None:
        self._s = _State()
        self._buffer: Deque[Dict] = deque()
        self._pending_comeout: bool = True  # always emit comeout at hand start

    # -------------------------
    # Private emitters
    # -------------------------

    def _emit(self, ev: Dict) -> None:
        """Push a canonicalized event into the FIFO buffer."""
        self._buffer.append(canonicalize_event(ev))

    def _emit_comeout_if_needed(self) -> None:
        if self._pending_comeout:
            self._emit({"type": COMEOUT, "roll_index": self._s.roll_index})
            self._pending_comeout = False
            self._s.on_comeout = True
            self._s.point = None

    # -------------------------
    # Public API
    # -------------------------

    def new_shooter(self, shooter_id: Optional[int]) -> None:
        """Advance to a new shooter. Resets hand context and schedules a comeout."""
        self._s.shooter_id = shooter_id
        self._s.point = None
        self._s.on_comeout = True
        self._emit({
            "type": "shooter_change",
            "shooter_id": shooter_id,
            "roll_index": self._s.roll_index,
        })
        self._pending_comeout = True

    def roll(self, total: int, dice: Optional[Tuple[int, int]] = None) -> None:
        """Consume a dice total and emit canonical events in proper order."""
        # increment roll index first (1-based)
        self._s.roll_index += 1
        self._emit_comeout_if_needed()

        # always emit the roll itself
        self._emit({
            "type": ROLL,
            "roll": int(total),
            "total": int(total),
            "dice": tuple(dice) if dice else None,
            "roll_index": self._s.roll_index,
            "point": self._s.point,
            "on_comeout": self._s.on_comeout,
        })

        # branch on table state
        if self._s.on_comeout:
            if total in _POINT_NUMBERS:
                # point established
                self._s.point = int(total)
                self._s.on_comeout = False
                self._emit({
                    "type": POINT_ESTABLISHED,
                    "point": self._s.point,
                    "roll_index": self._s.roll_index,
                    "on_comeout": False,
                })
            elif total in (7, 11, 2, 3, 12):
                # comeout naturals or craps — no extra events (remain on comeout)
                pass
        else:
            # point is on
            if total == 7:
                # seven-out ends hand → back to comeout next roll
                self._emit({"type": SEVEN_OUT, "roll_index": self._s.roll_index})
                self._s.point = None
                self._s.on_comeout = True
                self._pending_comeout = True

    def resolve(
        self,
        bet_type: str,
        result: str,
        payout: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> None:
        """Emit a canonical bet_resolved event."""
        self._emit({
            "type": "bet_resolved",
            "bet_type": str(bet_type),
            "result": str(result),
            "payout": float(payout) if payout is not None else None,
            "reason": str(reason) if reason is not None else None,
            "roll_index": self._s.roll_index,
            "point": self._s.point,
            "on_comeout": self._s.on_comeout,
        })

    def table_reset(self) -> None:
        """Hard reset of table/shooter context."""
        self._s = _State()
        self._pending_comeout = True

    # -------------------------
    # Accessors
    # -------------------------

    @property
    def point(self) -> Optional[int]:
        return self._s.point

    @property
    def shooter_id(self) -> Optional[int]:
        return self._s.shooter_id

    @property
    def roll_index(self) -> int:
        return self._s.roll_index

    # -------------------------
    # Drain
    # -------------------------

    def flush(self) -> Iterable[Dict]:
        """Yield and clear all pending events (FIFO)."""
        while self._buffer:
            yield self._buffer.popleft()


__all__ = ["EventStream"]