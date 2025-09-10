"""
Materialize bet intents onto a CrapsSim player, best-effort (duck-typed).
Supported intents: ("pass", None, amt), ("dont_pass", None, amt),
                   ("field", None, amt), ("place", number, amt),
                   ("__clear__", None, 0)
"""

from typing import Optional, Tuple, List

# Try to import common bet classes. If not present, we fall back to names.
try:
    from crapssim.bet import PassLine as _PassLine, DontPass as _DontPass, Field as _Field, Place as _Place  # type: ignore
except Exception:  # editing without engine available
    _PassLine = _DontPass = _Field = _Place = None  # type: ignore

BetIntent = Tuple[str, Optional[int], int]


def _bet_kind(obj) -> str:
    # Normalize a bet object's "kind" for matching
    k = getattr(obj, "kind", None)
    if isinstance(k, str):
        return k.lower()
    # fallback: class name
    return obj.__class__.__name__.lower()


def _bet_number(obj) -> Optional[int]:
    return getattr(obj, "number", None)


def _set_amount(obj, amount: int):
    # Common field name is "amount"; try that first.
    if hasattr(obj, "amount"):
        setattr(obj, "amount", int(amount))
        return True
    # Some engines might keep base on "base" or similar; try best effort.
    for attr in ("base", "wager", "value"):
        if hasattr(obj, attr):
            setattr(obj, attr, int(amount))
            return True
    return False


def _make_bet(kind: str, number: Optional[int], amount: int):
    # Construct a new bet object using engine classes when available.
    k = kind.lower()
    if k == "pass" and _PassLine is not None:
        return _PassLine(int(amount))
    if k == "dont_pass" and _DontPass is not None:
        return _DontPass(int(amount))
    if k == "field" and _Field is not None:
        return _Field(int(amount))
    if k == "place" and _Place is not None and number is not None:
        return _Place(int(number), int(amount))
    # Fallback: a tiny shim object with expected attributes so tests can run.
    class _Shim:
        def __init__(self, kind, number, amount):
            self.kind = kind
            self.number = number
            self.amount = int(amount)
            self.working = True
    return _Shim(k, number, amount)


def _find_existing(player, kind: str, number: Optional[int]):
    bets = getattr(player, "bets", None)
    if not bets:
        return None
    k = kind.lower()
    for b in list(bets):
        if _bet_kind(b) != k:
            continue
        if k == "place" and number is not None and _bet_number(b) != number:
            continue
        return b
    return None


def _add_bet(player, bet_obj) -> bool:
    """
    Try common ways to add a bet: player.add_bet(), player.place_bet(), append to player.bets
    Returns True if success.
    """
    for meth in ("add_bet", "place_bet", "add"):
        fn = getattr(player, meth, None)
        if callable(fn):
            try:
                fn(bet_obj)  # type: ignore
                return True
            except Exception:
                pass
    # Last resort: append directly if it's a list
    bets = getattr(player, "bets", None)
    if isinstance(bets, list):
        bets.append(bet_obj)
        return True
    return False


def _remove_bet(player, bet_obj) -> bool:
    # Try dedicated method first
    for meth in ("remove_bet", "drop_bet"):
        fn = getattr(player, meth, None)
        if callable(fn):
            try:
                fn(bet_obj)  # type: ignore
                return True
            except Exception:
                pass
    # Fallback: list remove
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
    # Try a method if present
    for meth in ("clear_bets", "remove_all_bets"):
        fn = getattr(player, meth, None)
        if callable(fn):
            try:
                fn()  # type: ignore
                return
            except Exception:
                pass


def apply_intents(player, intents: List[BetIntent]):
    """
    Apply a list of bet intents onto the player.
    Strategy: if a __clear__ sentinel is present, clear first, then lay down all intents.
    Otherwise, upsert each intent individually.
    """
    if not intents:
        return

    if any(k == "__clear__" for (k, _, _) in intents):
        _clear_all_bets(player)
        intents = [t for t in intents if t[0] != "__clear__"]

    for kind, number, amount in intents:
        if amount <= 0:
            # treat zero/negative as remove for that slot
            existing = _find_existing(player, kind, number)
            if existing is not None:
                _remove_bet(player, existing)
            continue

        existing = _find_existing(player, kind, number)
        if existing is not None:
            # Update amount
            if not _set_amount(existing, amount):
                # If we can’t set amount, replace the bet
                _remove_bet(player, existing)
                newb = _make_bet(kind, number, amount)
                _add_bet(player, newb)
        else:
            newb = _make_bet(kind, number, amount)
            _add_bet(player, newb)