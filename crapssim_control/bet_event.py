# crapssim_control/bet_event.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class BetEvent:
    """
    Lightweight bet transaction used by the ledger.

    Fields:
        bet:     Logical name of the bet (e.g., 'pass', 'place_8', 'lay_4').
        amount:  Stake amount relevant to this event.
        result:  Optional outcome label: 'win' | 'lose' | 'push' | None.
                 Use None when you're just recording a neutral transaction.
        payout:  If provided, use this exact bankroll delta.
                 If omitted, it's inferred from (result, amount):
                   - 'win'  => +amount
                   - 'lose' => -amount
                   - 'push' or None => 0.0
        meta:    Arbitrary structured extras (odds detail, units, roll id, etc.).
    """

    bet: str
    amount: float = 0.0
    result: Optional[str] = None
    payout: Optional[float] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def delta(self) -> float:
        """Bankroll delta for this event."""
        if self.payout is not None:
            return float(self.payout)
        if self.result == "win":
            return float(self.amount)
        if self.result == "lose":
            return -float(self.amount)
        # push or non-resolution
        return 0.0
