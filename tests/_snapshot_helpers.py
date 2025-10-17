"""Test helpers providing lightweight snapshot dataclasses used across regression tests."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


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
    dice: Optional[Tuple[int, int, int]]
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

