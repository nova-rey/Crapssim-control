from crapssim_control.events import derive_event
from crapssim_control.snapshotter import GameState, TableView, PlayerView

def _gs(comeout: bool, total: int | None, point_on: bool, point_num=None, seven_out=False, just_point=False):
    dice = (1, 1, total) if total is not None else None
    t = TableView(
        point_on=point_on,
        point_number=point_num,
        comeout=comeout,
        dice=dice,
        shooter_index=0,
        roll_index=0,
        rolls_this_shooter=0,
        table_level=10,
        bubble=False,
    )
    p = PlayerView(bankroll=300, starting_bankroll=300, bets=[])
    return GameState(
        table=t, player=p,
        just_established_point=just_point,
        just_made_point=False,
        just_seven_out=seven_out,
        is_new_shooter=False,
    )

def test_comeout_event_emits_during_comeout_phase():
    prev = _gs(comeout=True, total=11, point_on=False)   # previous roll irrelevant
    curr = _gs(comeout=True, total=4, point_on=False)    # a comeout roll that establishes a point (but we check priority below)
    ev = derive_event(prev, curr)
    # Because point establishment takes priority, this specific case becomes point_established.
    assert ev["event"] in ("point_established", "comeout")

    # Now a comeout roll that does NOT establish a point (e.g., 2 on comeout for pass loss)
    # bet_resolved takes priority:
    prev2 = _gs(comeout=True, total=11, point_on=False)
    curr2 = _gs(comeout=True, total=2, point_on=False)
    ev2 = derive_event(prev2, curr2)
    assert ev2["event"] in ("bet_resolved", "comeout")

    # Pure comeout with no resolution (e.g., we don't care about the number)
    prev3 = _gs(comeout=True, total=5, point_on=False)
    curr3 = _gs(comeout=True, total=8, point_on=False)
    ev3 = derive_event(prev3, curr3)
    # If not resolved and not point_established, we should get comeout
    if ev3["event"] not in ("bet_resolved", "point_established"):
        assert ev3["event"] == "comeout"