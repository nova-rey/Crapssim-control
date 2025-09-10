from dataclasses import dataclass, asdict
from typing import Optional, List, Tuple

@dataclass
class BetView:
    kind: str
    number: Optional[int]
    amount: int
    odds_amount: Optional[int] = None
    working: bool = True

@dataclass
class TableView:
    point_on: bool
    point_number: Optional[int]
    comeout: bool
    dice: Optional[Tuple[int,int,int]]   # (d1,d2,total)
    shooter_index: int
    roll_index: int
    rolls_this_shooter: int
    table_level: int
    bubble: bool

@dataclass
class PlayerView:
    bankroll: int
    starting_bankroll: int
    bets: List[BetView]

@dataclass
class GameState:
    table: TableView
    player: PlayerView
    just_established_point: bool = False
    just_made_point: bool = False
    just_seven_out: bool = False
    is_new_shooter: bool = False

class Snapshotter:
    @staticmethod
    def _read_point(table):
        point = getattr(table, "point", None)
        status = getattr(point, "status", "Off")
        number = getattr(point, "number", None)
        return status == "On", number

    @staticmethod
    def _read_dice(table):
        dice = getattr(table, "dice", None)
        d1 = getattr(dice, "die1", None)
        d2 = getattr(dice, "die2", None)
        total = getattr(dice, "total", None)
        if total is None and d1 is not None and d2 is not None:
            total = int(d1) + int(d2)
        if d1 is None or d2 is None or total is None:
            return None
        return (int(d1), int(d2), int(total))

    @staticmethod
    def _read_bets(player) -> List[BetView]:
        out: List[BetView] = []
        for b in getattr(player, "bets", []) or []:
            kind = getattr(b, "kind", b.__class__.__name__).lower()
            number = getattr(b, "number", None)
            amount = int(getattr(b, "amount", 0))
            working = bool(getattr(b, "working", True))
            odds_amount = getattr(b, "odds_amount", None)
            odds_amount = int(odds_amount) if odds_amount is not None else None
            out.append(BetView(kind=kind, number=number, amount=amount, odds_amount=odds_amount, working=working))
        return out

    @staticmethod
    def _derive_flags(prev: Optional[GameState], curr: TableView, dice_total: Optional[int]):
        if prev is None:
            return False, False, False, True  # first tick → new shooter
        just_established = (not prev.table.point_on) and curr.point_on
        just_made = prev.table.point_on and (not curr.point_on) and (dice_total == prev.table.point_number)
        just_seven = prev.table.point_on and (dice_total == 7)
        is_new_shooter = curr.comeout and (prev.just_seven_out or prev.just_made_point)
        return just_established, just_made, just_seven, is_new_shooter

    @staticmethod
    def capture(table, player, prev: Optional[GameState]) -> GameState:
        point_on, point_number = Snapshotter._read_point(table)
        dice = Snapshotter._read_dice(table)
        dice_total = dice[2] if dice else None

        shooter_index = int(getattr(table, "n_shooters", 0))
        roll_index = int(getattr(table, "n_rolls", 0))
        rolls_this_shooter = int(getattr(table, "n_rolls_this_shooter", 0))

        # Table rules come from spec later; default placeholders:
        strat = getattr(player, "strategy", None)
        table_level = int(getattr(strat, "table_level", 10))
        bubble = bool(getattr(strat, "bubble", False))

        comeout = not point_on

        bankroll = int(getattr(player, "bankroll", 0))
        starting_bankroll = int(getattr(player, "starting_bankroll", bankroll))
        bets = Snapshotter._read_bets(player)

        tview = TableView(point_on, point_number, comeout, dice,
                          shooter_index, roll_index, rolls_this_shooter,
                          table_level, bubble)
        pview = PlayerView(bankroll, starting_bankroll, bets)

        je, jm, js, ins = Snapshotter._derive_flags(prev, tview, dice_total)
        return GameState(tview, pview, je, jm, js, ins)

    @staticmethod
    def to_dict(gs: "GameState") -> dict:
        return asdict(gs)