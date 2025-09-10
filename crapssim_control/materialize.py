# crapssim_control/materialize.py
"""
Materialize bet intents onto a CrapsSim player, best-effort (duck-typed).

Supported intents:
  ("pass", None, amt, meta),
  ("dont_pass", None, amt, meta),
  ("field", None, amt, meta),
  ("come", None, amt, meta),
  ("dont_come", None, amt, meta),
  ("place", number, amt, meta),
  ("__clear__", None, 0, {})
"""

from typing import Optional, Tuple, List, Dict, Any
from .legalize import legalize_odds, legalize_lay_odds

# Try to import common bet classes. If not present, we fall back to names.
try:
    from crapssim.bet import PassLine as _PassLine, DontPass as _DontPass, Field as _Field, Place as _Place  # type: ignore
    from crapssim.bet import Come as _Come, DontCome as _DontCome  # type: ignore
except Exception:  # editing without engine available
    _PassLine = _DontPass = _Field = _Place = None  # type: ignore
    _Come = _DontCome = None  # type: ignore

BetIntent = Tuple[str, Optional[int], int, Dict[str, Any]]


def _bet_kind(obj) -> str:
    k = getattr(obj, "kind", None)
    if isinstance(k, str):
        return k.lower()
    return obj.__class__.__name__.lower()

def _bet_number(obj) -> Optional[int]:
    return getattr(obj, "number", None)

def _set_amount(obj, amount: int):
    if hasattr(obj, "amount"):
        setattr(obj, "amount", int(amount))
        return True
    for attr in ("base", "wager", "value"):
        if hasattr(obj, attr):
            setattr(obj, attr, int(amount))
            return True
    return False

def _set_working(obj, working: Optional[bool]):
    if working is None:
        return
    if hasattr(obj, "working"):
        try:
            setattr(obj, "working", bool(working))
            return
        except Exception:
            pass

def _set_odds(obj, odds: Optional[int]):
    if odds is None:
        return
    for attr in ("odds_amount", "odds", "lay_odds"):
        if hasattr(obj, attr):
            try:
                setattr(obj, attr, int(odds))
                return
            except Exception:
                pass

def _make_bet(kind: str, number: Optional[int], amount: int):
    k = kind.lower()
    if k == "pass" and _PassLine is not None:
        return _PassLine(int(amount))
    if k == "dont_pass" and _DontPass is not None:
        return _DontPass(int(amount))
    if k == "field" and _Field is not None:
        return _Field(int(amount))
    if k == "place" and _Place is not None and number is not None:
        return _Place(int(number), int(amount))
    if k == "come" and _Come is not None:
        return _Come(int(amount))
    if k == "dont_come" and _DontCome is not None:
        return _DontCome(int(amount))
    # Fallback shim object so tests can run without the engine.
    class _Shim:
        def __init__(self, kind, number, amount):
            self.kind = kind
            self.number = number
            self.amount = int(amount)
            self.working = True
            # provide common attributes used elsewhere
            self.odds_amount = 0    # pass/come odds
            self.lay_odds = 0       # dp/dc lay odds
    return _Shim(k, number, amount)

def _find_existing(player, kind: str, number: Optional[int]):
    bets = getattr(player, "bets", None)
    if not bets:
        return None
    k = kind.lower()
    for b in list(bets):
        if _bet_kind(b) != k:
            continue
        # For place bets, number must match. For others, number is usually None.
        if k == "place" and number is not None and _bet_number(b) != number:
            continue
        return b
    return None

def _add_bet(player, bet_obj) -> bool:
    for meth in ("add_bet", "place_bet", "add"):
        fn = getattr(player, meth, None)
        if callable(fn):
            try:
                fn(bet_obj)  # type: ignore
                return True
            except Exception:
                pass
    bets = getattr(player, "bets", None)
    if isinstance(bets, list):
        bets.append(bet_obj)
        return True
    return False

def _remove_bet(player, bet_obj) -> bool:
    for meth in ("remove_bet", "drop_bet"):
        fn = getattr(player, meth, None)
        if callable(fn):
            try:
                fn(bet_obj)  # type: ignore
                return True
            except Exception:
                pass
    bets = getattr(player, "bets", None)
    if isinstance(bets, list) and bet_obj in bets:
        bets.remove(bet_obj)
        return True
    return False

def _clear_all_bets(player):
    bets = getattr(player, "bets", None)
    if isinstance(bets, list):
        bets[:] = []
        return
    for meth in ("clear_bets", "remove_all_bets"):
        fn = getattr(player, meth, None)
        if callable(fn):
            try:
                fn()  # type: ignore
                return
            except Exception:
                pass

def _apply_meta_with_legalization(player, bet_obj, kind: str, meta: Dict[str, Any], odds_policy: str | int | None):
    if not meta:
        return
    _set_working(bet_obj, meta.get("working"))

    # PASS/DP odds already handled earlier; Come/DC odds are deferred for v0
    # because they require per-bet point numbers after movement.
    if "odds" in meta:
        if kind == "pass":
            table = getattr(player, "table", None)
            point = getattr(table, "point_number", None) if table else None
            bubble = bool(getattr(table, "bubble", False)) if table else False
            base_flat = int(getattr(bet_obj, "amount", 0))
            policy = odds_policy if odds_policy is not None else "3-4-5x"
            legalized = legalize_odds(point, int(meta["odds"]), base_flat, bubble=bubble, policy=policy)
            _set_odds(bet_obj, legalized)
        elif kind == "dont_pass":
            table = getattr(player, "table", None)
            point = getattr(table, "point_number", None) if table else None
            bubble = bool(getattr(table, "bubble", False)) if table else False
            base_flat = int(getattr(bet_obj, "amount", 0))
            policy = odds_policy if odds_policy is not None else "3-4-5x"
            legalized = legalize_lay_odds(point, int(meta["odds"]), base_flat, bubble=bubble, policy=policy)
            if hasattr(bet_obj, "lay_odds"):
                setattr(bet_obj, "lay_odds", int(legalized))
            else:
                _set_odds(bet_obj, legalized)
        else:
            # come / dont_come: odds intentionally ignored in v0
            pass

def apply_intents(player, intents: List[BetIntent], *, odds_policy: str | int | None = None):
    """
    Apply a list of bet intents onto the player.
    Strategy: if a __clear__ sentinel is present, clear first, then lay down all intents.
    Otherwise, upsert each intent individually.

    odds_policy: table-level odds policy ("3-4-5x", "2x", "5x", "10x", or int)
    """
    if not intents:
        return

    if any(k == "__clear__" for (k, *rest) in intents):
        _clear_all_bets(player)
        intents = [t for t in intents if t[0] != "__clear__"]

    for item in intents:
        # Allow both 3-tuple (legacy) and 4-tuple (with meta)
        if len(item) == 3:
            kind, number, amount = item  # type: ignore
            meta: Dict[str, Any] = {}
        else:
            kind, number, amount, meta = item  # type: ignore

        if amount <= 0:
            existing = _find_existing(player, kind, number)
            if existing is not None:
                _remove_bet(player, existing)
            continue

        existing = _find_existing(player, kind, number)
        if existing is not None:
            if not _set_amount(existing, amount):
                _remove_bet(player, existing)
                newb = _make_bet(kind, number, amount)
                _add_bet(player, newb)
                existing = newb
            _apply_meta_with_legalization(player, existing, kind, meta, odds_policy)
        else:
            newb = _make_bet(kind, number, amount)
            _add_bet(player, newb)
            _apply_meta_with_legalization(player, newb, kind, meta, odds_policy)