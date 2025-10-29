# tests/test_pnl_vars.py
from crapssim_control.varstore import VarStore

from tests._snapshot_helpers import GameState, TableView, PlayerView


def _gs(bankroll, starting, shooter_index, is_new_shooter=False):
    t = TableView(
        point_on=False,
        point_number=None,
        comeout=True,
        dice=(3, 4, 7),  # arbitrary
        shooter_index=shooter_index,
        roll_index=0,
        rolls_this_shooter=0,
        table_level=10,
        bubble=False,
    )
    p = PlayerView(bankroll=bankroll, starting_bankroll=starting, bets=[])
    return GameState(
        table=t,
        player=p,
        just_established_point=False,
        just_made_point=False,
        just_seven_out=False,
        is_new_shooter=is_new_shooter,
    )


def test_pnl_session_and_shooter_reset():
    vs = VarStore.from_spec({"variables": {}})
    # First snapshot: session starts at 300, shooter starts at 300
    gs1 = _gs(bankroll=300, starting=300, shooter_index=0, is_new_shooter=True)
    vs.refresh_system(gs1)
    assert vs.system["pnl_session"] == 0
    assert vs.system["pnl_shooter"] == 0
    assert vs.system["session_start_bankroll"] == 300
    assert vs.system["shooter_start_bankroll"] == 300

    # Profit within same shooter
    gs2 = _gs(bankroll=320, starting=300, shooter_index=0, is_new_shooter=False)
    vs.refresh_system(gs2)
    assert vs.system["pnl_session"] == 20
    assert vs.system["pnl_shooter"] == 20

    # New shooter, shooter anchor resets at current bankroll (325)
    gs3 = _gs(bankroll=325, starting=300, shooter_index=1, is_new_shooter=True)
    vs.refresh_system(gs3)
    assert vs.system["pnl_session"] == 25
    assert vs.system["pnl_shooter"] == 0
    assert vs.system["shooter_start_bankroll"] == 325
