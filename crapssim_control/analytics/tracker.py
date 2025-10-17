"""Bankroll and roll-tracking analytics helper."""

from __future__ import annotations

from .types import HandCtx, RollCtx, SessionCtx


class Tracker:
    """Lightweight runtime tracker used for additive analytics exports."""

    def __init__(self, config):
        self.config = config
        self.bankroll = 0.0
        self.bankroll_peak = 0.0
        self.bankroll_low = 0.0
        self.max_drawdown = 0.0
        self.hand_id = 0
        self.roll_in_hand = 0

    def on_session_start(self, ctx: SessionCtx) -> None:
        self.bankroll = ctx.bankroll
        self.bankroll_peak = ctx.bankroll
        self.bankroll_low = ctx.bankroll
        self.max_drawdown = 0.0

    def on_session_end(self, ctx: SessionCtx) -> None:
        # Mirror latest bankroll state in case caller updated context.
        self.bankroll = ctx.bankroll
        self.bankroll_peak = max(self.bankroll_peak, self.bankroll)
        self.bankroll_low = min(self.bankroll_low, self.bankroll)
        self.max_drawdown = max(self.max_drawdown, self.bankroll_peak - self.bankroll)

    def on_hand_start(self, hand_ctx: HandCtx) -> None:
        self.hand_id += 1
        self.roll_in_hand = 0

    def on_hand_end(self, hand_ctx: HandCtx) -> None:
        # No additional bookkeeping yet; placeholder for future summaries.
        return None

    def on_roll(self, roll_ctx: RollCtx) -> None:
        self.roll_in_hand += 1
        self.bankroll = roll_ctx.bankroll_before + roll_ctx.delta
        self.bankroll_peak = max(self.bankroll_peak, self.bankroll)
        self.bankroll_low = min(self.bankroll_low, self.bankroll)
        self.max_drawdown = max(self.max_drawdown, self.bankroll_peak - self.bankroll)

    def get_roll_snapshot(self) -> dict[str, float | int]:
        return {
            "hand_id": self.hand_id,
            "roll_in_hand": self.roll_in_hand,
            "bankroll_after": self.bankroll,
            "drawdown_after": self.bankroll_peak - self.bankroll,
        }

    def get_summary_snapshot(self) -> dict[str, float]:
        return {
            "bankroll_peak": self.bankroll_peak,
            "bankroll_low": self.bankroll_low,
            "max_drawdown": self.max_drawdown,
        }
