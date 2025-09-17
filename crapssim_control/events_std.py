"""
events_std.py -- Batch 13: Canonical event stream for ControlStrategy

This module provides a small, engine-agnostic event derivation state machine.
It turns basic "facts" (new shooter, dice totals, bet resolutions) into a
clean, canonical stream of events the rule engine can consume *in order*.

It is intentionally narrow and schema-stable so the controller and compiler
can target the same contract.

Canonical events (dicts):
  - {"type": "shooter_change", "shooter_id": int, "roll_index": int}
  - {"type": "comeout", "roll_index": int}
  - {"type": "point_established", "point": int, "roll_index": int}
  - {"type": "roll", "total": int, "dice": (d1, d2) | None, "roll_index": int}
  - {"type": "seven_out", "roll_index": int}
  - {"type": "bet_resolved",
     "bet_type": str,           # canonical when possible
     "result": "win"|"loss"|"push",
     "payout": float | None,    # full return incl winnings if available
     "reason": str | None,      # optional text from engine/adapter
     "roll_index": int}

Usage pattern (example):
    es = EventStream()
    es.new_shooter(shooter_id=1)
    es.roll(6, (3, 3))     # emits: comeout, roll(6), point_established(6)
    es.roll(8, (4, 4))     # emits: roll(8)
    es.resolve("place_6", "win", payout=14)  # emits: bet_resolved(...)
    es.roll(7, (3, 4))     # emits: roll(7), seven_out

    for ev in es.flush():
        controller.handle(ev)

Design choices:
  - We maintain minimal table state: current point, whether we’re on comeout,
    a monotonic roll_index, and a current shooter id.
  - We emit `comeout` exactly once at the start of a hand and right after seven-out.
  - We emit `point_established` when a 4/5/6/8/9/10 appears on comeout.
  - We emit `seven_out` when a 7 appears while a point is on.
  - We do NOT infer anything about bets; `resolve(...)` takes explicit bet resolution facts
    from your engine adapter and turns them into canonical `bet_resolved` events.

This module is additive and does not change existing events.py behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Deque, Dict, Iterable, List, Optional, Tuple
from collections import deque


_POINT_NUMBERS = {4, 5, 6, 8, 9, 10}


@dataclass
class _State:
    shooter_id: Optional[int] = None
    point: Optional[int] = None
    on_comeout: bool = True
    roll_index: int = 0


class EventStream:
    """
    Small state machine that derives canonical control events from simple inputs.

    Call sequence:
      - new_shooter(shooter_id)         # optional between hands; forces comeout
      - roll(total, dice=None)          # per dice roll
      - resolve(bet_type, result, ...)  # bet result facts (optional, any time)
      - flush()                         # iterate and clear emitted events
    """
    def __init__(self) -> None:
        self._s = _State()
        self._buffer: Deque[Dict] = deque()
        self._pending_comeout: bool = True  # emit comeout at first roll by default

    # -------------------------
    # Emit helpers
    # -------------------------

    def _emit(self, ev: Dict) -> None:
        self._buffer.append(ev)

    def _emit_comeout_if_needed(self) -> None:
        if self._pending_comeout:
            self._emit({"type": "comeout", "roll_index": self._s.roll_index})
            self._pending_comeout = False
            self._s.on_comeout = True
            self._s.point = None

    # -------------------------
    # Public API
    # -------------------------

    def new_shooter(self, shooter_id: Optional[int]) -> None:
        """
        Advance to a new shooter. This resets hand context and schedules a 'comeout'.
        """
        self._s.shooter_id = shooter_id
        self._s.point = None
        self._s.on_comeout = True
        # do not increment roll_index here; first roll will
        self._emit({
            "type": "shooter_change",
            "shooter_id": shooter_id,
            "roll_index": self._s.roll_index,
        })
        self._pending_comeout = True

    def roll(self, total: int, dice: Optional[Tuple[int, int]] = None) -> None:
        """
        Consume a dice roll and emit standardized events in proper order.
        """
        # increment roll index first (rolls are 1-based for most consumers)
        self._s.roll_index += 1

        # comeout gate
        self._emit_comeout_if_needed()

        # roll event itself
        self._emit({
            "type": "roll",
            "total": int(total),
            "dice": tuple(dice) if dice is not None else None,
            "roll_index": self._s.roll_index,
        })

        # branch on table state
        if self._s.on_comeout:
            if total in _POINT_NUMBERS:
                # point established
                self._s.point = int(total)
                self._s.on_comeout = False
                self._emit({
                    "type": "point_established",
                    "point": self._s.point,
                    "roll_index": self._s.roll_index,
                })
            elif total in (7, 11):
                # natural comeout winner – nothing else to emit
                pass
            elif total in (2, 3, 12):
                # comeout craps – nothing else to emit (hand continues on comeout)
                pass
            # otherwise remain on comeout
        else:
            # point is on
            if total == 7:
                # seven out -- hand ends, back to comeout next roll
                self._emit({"type": "seven_out", "roll_index": self._s.roll_index})
                self._s.point = None
                self._s.on_comeout = True
                self._pending_comeout = True
            # hitting the point (e.g., total == self._s.point) is just another roll
            # ControlStrategy rules can react to "roll" + knowledge of `point`
            # if they need (we keep the event minimal on purpose)

    def resolve(
        self,
        bet_type: str,
        result: str,
        payout: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> None:
        """
        Emit a canonical bet_resolved event. Call this from your engine adapter when a bet closes.
        """
        self._emit({
            "type": "bet_resolved",
            "bet_type": str(bet_type),
            "result": str(result),
            "payout": float(payout) if payout is not None else None,
            "reason": str(reason) if reason is not None else None,
            "roll_index": self._s.roll_index,
        })

    def table_reset(self) -> None:
        """
        Optional: reset entire table/shooter context (e.g., when the engine restarts).
        """
        self._s = _State(
            shooter_id=None,
            point=None,
            on_comeout=True,
            roll_index=0,
        )
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

    def flush(self) -> Iterable[Dict]:
        """
        Yield and clear all pending events (FIFO).
        """
        while self._buffer:
            yield self._buffer.popleft()