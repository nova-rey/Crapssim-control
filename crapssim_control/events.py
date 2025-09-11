from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TableView:
    point_on: bool
    point_number: Optional[int]
    comeout: bool
    dice: Tuple[int, int, int]  # d1, d2, total
    shooter_index: int
    roll_index: int
    bankroll: float
    bets: List[Dict[str, Any]]


@dataclass
class GameState:
    table: TableView
    just_established_point: bool
    just_made_point: bool
    just_seven_out: bool
    is_new_shooter: bool


def _bet_as_dict(b: Any) -> Dict[str, Any]:
    return {
        "kind": getattr(b, "kind", getattr(b, "name", "unknown")),
        "number": getattr(b, "number", None),
        "amount": float(getattr(b, "amount", 0.0)),
    }


def _extract(table: Any) -> GameState:
    # Adapter or tests provide attributes with these names; keep this tolerant.
    tv = TableView(
        point_on=bool(getattr(table, "point_on", False)),
        point_number=getattr(table, "point_number", None),
        comeout=bool(getattr(table, "comeout", False)),
        dice=(getattr(table, "d1", 1), getattr(table, "d2", 1), getattr(table, "total", getattr(table, "sum", 2))),
        shooter_index=int(getattr(table, "shooter_index", 0)),
        roll_index=int(getattr(table, "roll_index", 0)),
        bankroll=float(getattr(getattr(table, "player", None), "bankroll", 0.0)),
        bets=[_bet_as_dict(b) for b in getattr(getattr(table, "player", None), "bets", [])],
    )
    return GameState(
        table=tv,
        just_established_point=bool(getattr(table, "just_established_point", False)),
        just_made_point=bool(getattr(table, "just_made_point", False)),
        just_seven_out=bool(getattr(table, "just_seven_out", False)),
        is_new_shooter=bool(getattr(table, "is_new_shooter", False)),
    )


def capture_table_state(table: Any) -> Dict[str, Any]:
    """Snapshot the table/player into a plain dict (what the rules engine expects)."""
    gs = _extract(table)
    return _gamestate_to_snapshot(gs)


def _gamestate_to_snapshot(gs: GameState) -> Dict[str, Any]:
    tv = gs.table
    return {
        "point_on": tv.point_on,
        "point_number": tv.point_number,
        "comeout": tv.comeout,
        "dice": tv.dice,
        "shooter_index": tv.shooter_index,
        "roll_index": tv.roll_index,
        "bankroll": tv.bankroll,
        "bets": tv.bets,
        "just_established_point": gs.just_established_point,
        "just_made_point": gs.just_made_point,
        "just_seven_out": gs.just_seven_out,
        "is_new_shooter": gs.is_new_shooter,
    }


def _to_snapshot(x: Optional[Dict[str, Any] | GameState]) -> Optional[Dict[str, Any]]:
    """Accept either our GameState or a dict snapshot and normalize to dict."""
    if x is None:
        return None
    if isinstance(x, dict):
        return x
    if isinstance(x, GameState):
        return _gamestate_to_snapshot(x)
    # Last resort: try attribute access similar to capture_table_state
    # if a foreign object shaped like GameState sneaks in.
    try:
        return _gamestate_to_snapshot(x)  # type: ignore[arg-type]
    except Exception:
        return None


def derive_event(prev: Optional[Dict[str, Any] | GameState], curr: Dict[str, Any] | GameState) -> Dict[str, Any]:
    """
    Turn raw table snapshots into a simple event dict consumed by the rules engine.

    Priority/contract (to satisfy tests):
      1) If a point is *just* established on a comeout roll -> {"event": "point_established"}
      2) Else if transitioning into comeout (or first snapshot on comeout) -> {"event": "comeout"}
      3) Otherwise -> {"event": "roll"}
    """
    prev_sn = _to_snapshot(prev)
    curr_sn = _to_snapshot(curr) or {}

    # Initial observation
    if prev_sn is None:
        if curr_sn.get("just_established_point"):
            return {"event": "point_established", "point": curr_sn.get("point_number")}
        return {"event": "comeout"} if curr_sn.get("comeout") else {"event": "roll"}

    # Point establishment takes priority if flagged
    if curr_sn.get("just_established_point"):
        return {"event": "point_established", "point": curr_sn.get("point_number")}

    # Transition into comeout (new shooter or point off)
    was_comeout = bool(prev_sn.get("comeout"))
    is_comeout = bool(curr_sn.get("comeout"))
    if is_comeout and not was_comeout:
        return {"event": "comeout"}

    return {"event": "roll"}