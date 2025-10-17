"""Stub analytics tracker for Phase 3 scaffolding (lightweight snapshots only)."""

from .types import HandCtx, RollCtx, SessionCtx


class Tracker:
    """Stub analytics tracker for Phase 3 scaffolding (lightweight, no heavy refs)."""

    def __init__(self, config):
        self.config = config
        self._events = []
        self.events = self._events
        self._session_ctx = None

    def on_session_start(self, ctx):
        bankroll = getattr(ctx, "bankroll", 0.0)
        session_ctx = SessionCtx(bankroll=bankroll)
        self._session_ctx = session_ctx
        self._events.append(("session_start", session_ctx))

    def on_session_end(self, ctx):
        bankroll = getattr(ctx, "bankroll", 0.0)
        session_ctx = self._session_ctx or SessionCtx(bankroll=bankroll)
        session_ctx.bankroll = bankroll
        self._session_ctx = session_ctx
        self._events.append(("session_end", session_ctx))

    def on_hand_start(self, hand_ctx):
        hand_id = getattr(hand_ctx, "hand_id", None)
        point = getattr(hand_ctx, "point", None)
        tracked = HandCtx(hand_id=hand_id, point=point)
        self._events.append(("hand_start", tracked))

    def on_hand_end(self, hand_ctx):
        hand_id = getattr(hand_ctx, "hand_id", None)
        point = getattr(hand_ctx, "point", None)
        tracked = HandCtx(hand_id=hand_id, point=point)
        self._events.append(("hand_end", tracked))

    def on_roll(self, roll_ctx):
        hand_id = getattr(roll_ctx, "hand_id", None)
        roll_number = getattr(roll_ctx, "roll_number", None)
        bankroll_before = getattr(roll_ctx, "bankroll_before", 0.0)
        self._events.append(("roll", RollCtx(
            hand_id=hand_id,
            roll_number=roll_number,
            bankroll_before=bankroll_before,
        )))
