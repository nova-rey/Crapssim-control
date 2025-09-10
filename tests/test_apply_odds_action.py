from crapssim_control.materialize import apply_intents
from crapssim_control.materialize import _make_bet  # using internal helper for a lightweight shim

class _TableShim:
    def __init__(self, bubble=False):
        self.bubble = bubble
        self.point_number = None  # not used for come/DC odds

class _PlayerShim:
    def __init__(self):
        self.table = _TableShim()
        self.bets = []

def test_apply_odds_on_come_all_and_newest():
    # Create player with two COME bets already moved to numbers (6, 8)
    p = _PlayerShim()
    b6 = _make_bet("come", 6, 10)  # flat 10 on 6
    b8 = _make_bet("come", 8, 10)  # flat 10 on 8
    p.bets.extend([b6, b8])

    # Apply odds 25 to all come bets (3-4-5x; step 5 on 6/8; cap 50)
    intents = [
        ("__apply_odds__", "come", 25, {"scope": "all"})
    ]
    apply_intents(p, intents, odds_policy="3-4-5x")
    assert getattr(b6, "odds_amount", 0) == 25
    assert getattr(b8, "odds_amount", 0) == 25

    # Now newest only with 47 → step 5 → 45 (cap 50)
    intents = [
        ("__apply_odds__", "come", 47, {"scope": "newest"})
    ]
    apply_intents(p, intents, odds_policy="3-4-5x")
    # Only b8 should change
    assert getattr(b6, "odds_amount", 0) == 25
    assert getattr(b8, "odds_amount", 0) == 45

def test_apply_odds_on_dont_come():
    p = _PlayerShim()
    d5 = _make_bet("dont_come", 5, 10)  # flat 10 on 5
    p.bets.append(d5)

    # DC lay odds desired 31; policy 3-4-5x → win-cap for 5 = 4x*10 = 40
    # lay-cap = floor(40*3/2)=60; step 3 → floor(31 to 30)
    intents = [
        ("__apply_odds__", "dont_come", 31, {"scope": "all"})
    ]
    apply_intents(p, intents, odds_policy="3-4-5x")
    # Attribute may be lay_odds or odds_amount depending on engine; our shim has lay_odds
    assert getattr(d5, "lay_odds", 0) == 30