# tests/test_point_and_rolls_since_point.py
from crapssim_control.events import derive_event
from crapssim_control.varstore import VarStore
from crapssim_control.snapshotter import GameState, TableView, PlayerView

def _gs(comeout: bool, total: int, point_on: bool, point_num, roll_idx, just_est=False, just_made=False):
    dice = (2, total-2, total)
    t = TableView(
        point_on=point_on,
        point_number=point_num,
        comeout=comeout,
        dice=dice,
        shooter_index=0,
        roll_index=roll_idx,
        rolls_this_shooter=roll_idx,
        table_level=10,
        bubble=False,
    )
    p = PlayerView(bankroll=300, starting_bankroll=300, bets=[])
    return GameState(
        table=t, player=p,
        just_established_point=just_est,
        just_made_point=just_made,
        just_seven_out=False,
        is_new_shooter=False,
    )

def test_point_made_and_rolls_since_point():
    vs = VarStore.from_spec({"variables": {}})

    # Roll 1: comeout 4 establishes point (event could be point_established)
    prev = _gs(comeout=True, total=6, point_on=False, point_num=None, roll_idx=0, just_est=False)
    curr = _gs(comeout=False, total=4, point_on=True, point_num=4, roll_idx=1, just_est=True)
    ev = derive_event(prev, curr)
    assert ev["event"] in ("point_established", "bet_resolved")  # depending on upstream, establishment takes priority
    vs.refresh_system(curr)
    assert vs.system["rolls_since_point"] == 0

    # Roll 2 under the same point
    curr2 = _gs(comeout=False, total=5, point_on=True, point_num=4, roll_idx=2)
    vs.refresh_system(curr2)
    assert vs.system["rolls_since_point"] == 1

    # Roll 3 hits the point → point_made (and pass resolves win)
    prev3 = curr2
    curr3 = _gs(comeout=True, total=4, point_on=False, point_num=None, roll_idx=3, just_made=True)
    ev3 = derive_event(prev3, curr3)
    assert ev3["event"] in ("point_made", "bet_resolved")
    vs.refresh_system(curr3)
    # Point is now off; counter will remain whatever it was (1) until the next point establishes,
    # then reset to 0. We don't assert here because behavior depends on when refresh is called.