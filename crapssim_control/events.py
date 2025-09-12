# crapssim_control/events.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict


class EventType(Enum):
    """High-level event types seen by the tracker/simulator."""
    ROLL = auto()
    POINT_ESTABLISHED = auto()
    POINT_MADE = auto()
    SEVEN_OUT = auto()
    COMEOUT = auto()


# ------------ Dice / Table Events ------------

@dataclass(frozen=True)
class RollEvent:
    """A single dice roll."""
    value: int
    is_comeout: bool = False


@dataclass(frozen=True)
class PointEvent:
    """Point state change (established or cleared)."""
    point: Optional[int]  # number 4/5/6/8/9/10, or None/0 when point is off


# ------------ Betting Events (for ledger/tests) ------------

@dataclass(frozen=True)
class BetEvent:
    """
    A lightweight bet resolution/transaction event for the ledger.

    Fields:
        bet:     Name/identifier of the bet (e.g., 'pass', 'place_8', etc.)
        amount:  Stake amount relevant to this event (typically the wager).
        result:  Optional resolution result: 'win' | 'lose' | 'push' (None if not a resolution).
        payout:  Explicit bankroll delta. If provided, it is used directly.
                 If not provided, delta is inferred from (result, amount).
                 win  -> +amount
                 lose -> -amount
                 push/None -> 0
        meta:    Optional extra data for downstream consumers (odds, units, etc.)
    """
    bet: str
    amount: float = 0.0
    result: Optional[str] = None        # 'win' | 'lose' | 'push' | None
    payout: Optional[float] = None      # if set, used as the bankroll delta
    meta: Dict[str, object] = field(default_factory=dict)

    @property
    def delta(self) -> float:
        """Computed bankroll delta for this bet event."""
        if self.payout is not None:
            return float(self.payout)
        if self.result == "win":
            return float(self.amount)
        if self.result == "lose":
            return -float(self.amount)
        # push or non-resolution
        return 0.0


__all__ = [
    "EventType",
    "RollEvent",
    "PointEvent",
    "BetEvent",
]