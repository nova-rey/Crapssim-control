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
        self.total_hands = 0
        self.total_rolls = 0
        self.points_made = 0
        self.pso_count = 0
        self._point_active = False
        self._current_point: int | None = None
        self._rolls_since_point = 0

    def on_session_start(self, ctx: SessionCtx) -> None:
        self.bankroll = ctx.bankroll
        self.bankroll_peak = ctx.bankroll
        self.bankroll_low = ctx.bankroll
        self.max_drawdown = 0.0
        self.hand_id = 0
        self.roll_in_hand = 0
        self.total_hands = 0
        self.total_rolls = 0
        self.points_made = 0
        self.pso_count = 0
        self._point_active = False
        self._current_point = None
        self._rolls_since_point = 0

    def on_session_end(self, ctx: SessionCtx) -> None:
        # Mirror latest bankroll state in case caller updated context.
        self.bankroll = ctx.bankroll
        self.bankroll_peak = max(self.bankroll_peak, self.bankroll)
        self.bankroll_low = min(self.bankroll_low, self.bankroll)
        self.max_drawdown = max(self.max_drawdown, self.bankroll_peak - self.bankroll)

    def on_hand_start(self, hand_ctx: HandCtx) -> None:
        self.hand_id += 1
        self.roll_in_hand = 0
        self.total_hands += 1
        self._current_point = hand_ctx.point
        self._point_active = bool(hand_ctx.point)
        self._rolls_since_point = 0

    def on_hand_end(self, hand_ctx: HandCtx) -> None:
        # No additional bookkeeping yet; placeholder for future summaries.
        self._point_active = False
        self._current_point = None
        self._rolls_since_point = 0
        return None

    def on_roll(self, roll_ctx: RollCtx) -> None:
        self.roll_in_hand += 1
        self.total_rolls += 1
        self.bankroll = roll_ctx.bankroll_before + roll_ctx.delta
        self.bankroll_peak = max(self.bankroll_peak, self.bankroll)
        self.bankroll_low = min(self.bankroll_low, self.bankroll)
        self.max_drawdown = max(self.max_drawdown, self.bankroll_peak - self.bankroll)

        event_type = (roll_ctx.event_type or "").lower()
        point_value = roll_ctx.point
        point_on = bool(roll_ctx.point_on)

        if event_type == "point_established":
            if point_value is not None:
                self._point_active = True
                self._current_point = point_value
            else:
                self._point_active = False
                self._current_point = None
            self._rolls_since_point = 0
        elif event_type == "roll":
            if self._point_active:
                self._rolls_since_point = max(self._rolls_since_point, roll_ctx.roll_number)
        elif event_type == "point_made":
            if self._point_active:
                self.points_made += 1
            self._point_active = False
            self._current_point = None
            self._rolls_since_point = 0
        elif event_type == "seven_out":
            if self._point_active and self._rolls_since_point == 0 and roll_ctx.roll_number == 0:
                self.pso_count += 1
            self._point_active = False
            self._current_point = None
            self._rolls_since_point = 0
        elif event_type == "comeout":
            self._point_active = False
            self._current_point = None
            self._rolls_since_point = 0

        if not point_on:
            self._point_active = False
            self._current_point = None
            self._rolls_since_point = 0

    def get_roll_snapshot(self) -> dict[str, float | int]:
        return {
            "hand_id": self.hand_id,
            "roll_in_hand": self.roll_in_hand,
            "bankroll_after": self.bankroll,
            "drawdown_after": self.bankroll_peak - self.bankroll,
        }

    def get_summary_snapshot(self) -> dict[str, float | int]:
        return {
            "total_hands": self.total_hands,
            "total_rolls": self.total_rolls,
            "points_made": self.points_made,
            "pso_count": self.pso_count,
            "bankroll_peak": self.bankroll_peak,
            "bankroll_low": self.bankroll_low,
            "max_drawdown": self.max_drawdown,
        }
