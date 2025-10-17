"""Stub analytics tracker for Phase 3 scaffolding."""


class Tracker:
    """Stub analytics tracker for Phase 3 scaffolding."""

    def __init__(self, config):
        self.config = config
        self.events = []

    def on_session_start(self, ctx):
        self.events.append(("session_start", ctx))

    def on_session_end(self, ctx):
        self.events.append(("session_end", ctx))

    def on_hand_start(self, hand_ctx):
        self.events.append(("hand_start", hand_ctx))

    def on_hand_end(self, hand_ctx):
        self.events.append(("hand_end", hand_ctx))

    def on_roll(self, roll_ctx):
        self.events.append(("roll", roll_ctx))
