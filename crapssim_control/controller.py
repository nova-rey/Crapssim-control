try:
    from crapssim.strategy.tools import Strategy
except Exception:
    class Strategy:  # fallback for editing
        def update_bets(self, player): ...
        def completed(self, player): return False
        def after_roll(self, player): ...

from .snapshotter import Snapshotter

class ControlStrategy(Strategy):
    """v0 scaffold: keeps a last_state snapshot per roll."""
    def __init__(self, spec: dict):
        self.spec = spec or {}
        self.last_state = None

    def update_bets(self, player):
        if self.last_state is None:
            self.last_state = Snapshotter.capture(player.table, player, prev=None)
        # (rules + templates come later)

    def after_roll(self, player):
        self.last_state = Snapshotter.capture(player.table, player, prev=self.last_state)

    def completed(self, player):
        return False