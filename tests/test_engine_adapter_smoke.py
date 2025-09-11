# tests/test_engine_adapter_smoke.py
from crapssim_control.engine_adapter import EngineAdapter
from crapssim_control.controller import ControlStrategy

class _FakeBet:
    def __init__(self, kind="field", number=None, amount=5.0):
        self.kind = kind
        self.number = number
        self.amount = amount

class _FakePlayer:
    def __init__(self, bankroll=1000.0):
        self.bankroll = bankroll
        self.bets = []

class _FakeTable:
    def __init__(self):
        self.point = 0
        self.last_total = 0
        self.current_player = _FakePlayer()
        self._rolls = [3, 7]  # field win then field lose

    def add_player(self, p):
        self.current_player = p

    def roll_once(self):
        # simple: pop a total and update bankroll roughly
        if not self._rolls:
            self._rolls = [7]
        t = self._rolls.pop(0)
        self.last_total = t
        # settle a single field bet at even money
        wins = t in (2,3,4,9,10,11)
        for b in list(self.current_player.bets):
            if b.kind == "field":
                if wins:
                    self.current_player.bankroll += b.amount
                else:
                    self.current_player.bankroll -= b.amount

def test_adapter_runs_without_engine():
    spec = {
        "meta": {"version": 0, "name": "Adapter Smoke"},
        "table": {"bubble": True, "level": 5},
        "variables": {"units": 5},
        "modes": {"Main": {"template": {"field": "units"}}},
        "rules": [
            {"on":{"event":"comeout"}, "do":["apply_template('Main')"]}
        ]
    }
    player = _FakePlayer()
    table = _FakeTable()
    table.add_player(player)

    strat = ControlStrategy(spec)
    # seed one field bet so unambiguous resolution path triggers
    player.bets.append(_FakeBet(kind="field", amount=5.0))

    adapter = EngineAdapter(table, player, strat)
    adapter.play(shooters=1)

    assert True  # just don’t crash