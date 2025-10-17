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

  Special control intents:
  ("__clear__", None, 0, {})
  ("__apply_odds__", <'come'|'dont_come'>, desired_odds, {"scope": "all"|"newest"})
"""

from typing import Optional, Tuple, List, Dict, Any
from .legalize_legacy import legalize_odds, legalize_lay_odds

# Try engine bet classes; otherwise we use shims.
try:
    from crapssim.bet import PassLine as _PassLine, DontPass as _DontPass, Field as _Field, Place as _Place  # type: ignore
    from crapssim.bet import Come as _Come, DontCome as _DontCome  # type: ignore
except Exception:
    _PassLine = _DontPass = _Field = _Place = None  # type: ignore
    _Come = _DontCome = None  # type: ignore

BetIntent = Tuple[str, Optional[int], int, Dict[str, Any]]

# -------------------------- Kind normalization helpers -----------------------

_KIND_MAP = {
    # engine/class names → canonical
    "passline": "pass",
    "dontpass": "dont_pass",
    "dont_come": "dont_come",
    "dontcome": "dont_come",
    "come": "come",
    "field": "field",
    "place": "place",
    "pass": "pass",
    "dont_pass": "dont_pass",
}

def _norm(kind: str) -> str:
    return _KIND_MAP.get(kind.lower(), kind.lower())

# -------- Overlay wrapper to allow sidecar attributes (e.g., lay_odds) --------

class _BetOverlay:
    """
    Proxy that wraps a real bet object and provides a sidecar for attributes
    the engine object doesn't support (e.g., lay_odds on DontCome).
    """
    __slots__ = ("_obj", "_extra")

    def __init__(self, obj):
        object.__setattr__(self, "_obj", obj)
        object.__setattr__(self, "_extra", {})  # sidecar dict

    def __getattr__(self, name):
        extra = object.__getattribute__(self, "_extra")
        if name in extra:
            return extra[name]
        obj = object.__getattribute__(self, "_obj")
        return getattr(obj, name)

    def __setattr__(self, name, value):
        obj = object.__getattribute__(self, "_obj")
        try:
            setattr(obj, name, value)
        except Exception:
            extra = object.__getattribute__(self, "_extra")
            extra[name] = value

    @property
    def __class__(self):
        return object.__getattribute__(self, "_obj").__class__

    def __repr__(self):
        obj = object.__getattribute__(self, "_obj")
        return f"<Overlay {obj!r} extra={object.__getattribute__(self, '_extra')}>"

# -----------------------------------------------------------------------------

def _bet_kind(obj) -> str:
    # prefer explicit kind if present
    k = getattr(obj, "kind", None)
    raw = k.lower() if isinstance(k, str) else obj.__class__.__name__.lower()
    return _norm(raw)

def _bet_number(obj) -> Optional[int]:
    return getattr(obj, "number", None)

def _set_amount(obj, amount: int) -> bool:
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
        except Exception:
            pass

def _set_odds_known_attrs(obj, odds: int) -> bool:
    """
    Try common attribute names for odds-like values. Return True if set.
    """
    for attr in ("odds_amount", "odds", "lay_odds"):
        if hasattr(obj, attr):
            try:
                setattr(obj, attr, int(odds))
                return True
            except Exception:
                pass
    # Nested odds objects (rare)
    nested = getattr(obj, "odds", None)
    if nested is not None:
        for attr in ("amount", "value"):
            if hasattr(nested, attr):
                try:
                    setattr(nested, attr, int(odds))
                    return True
                except Exception:
                    pass
    return False

def _force_sidecar_odds(obj, kind: str, odds: int):
    """
    As a last resort, dynamically attach attributes so tests & debug can read them.
    Overlay will always accept these. On plain objects, we try setattr and ignore errors.
    """
    k = _norm(kind)
    try:
        if k in ("dont_pass", "dont_come"):
            setattr(obj, "lay_odds", int(odds))
            setattr(obj, "odds_amount", int(odds))
        else:
            setattr(obj, "odds_amount", int(odds))
    except Exception:
        pass

def _mirror_lay_and_amount(obj, odds: int):
    """
    Ensure both lay_odds AND odds_amount reflect the same value (for DC).
    Works with overlays or permissive objects; silently ignores failures.
    """
    try:
        setattr(obj, "lay_odds", int(odds))
    except Exception:
        pass
    try:
        setattr(obj, "odds_amount", int(odds))
    except Exception:
        pass

def _wrap_if_needed(kind: str, obj):
    """
    Wrap COME / DON'T COME with an overlay so we can always stash odds attrs.
    Keep others raw (no need yet).
    """
    k = _norm(kind)
    if k in ("come", "dont_come"):
        return _BetOverlay(obj)
    return obj

def _make_bet(kind: str, number: Optional[int], amount: int):
    """
    Create a bet object. For Come / Don't Come using real engine classes,
    we post-set .number if provided so tests can simulate 'moved' bets,
    then wrap in an overlay so odds attrs can be attached reliably.
    """
    k = _norm(kind)
    if k == "pass" and _PassLine is not None:
        return _PassLine(int(amount))
    if k == "dont_pass" and _DontPass is not None:
        return _DontPass(int(amount))
    if k == "field" and _Field is not None:
        return _Field(int(amount))
    if k == "place" and _Place is not None and number is not None:
        return _Place(int(number), int(amount))
    if k == "come" and _Come is not None:
        obj = _Come(int(amount))
        if number is not None:
            try: setattr(obj, "number", int(number))
            except Exception: pass
        return _wrap_if_needed("come", obj)
    if k == "dont_come" and _DontCome is not None:
        obj = _DontCome(int(amount))
        if number is not None:
            try: setattr(obj, "number", int(number))
            except Exception: pass
        return _wrap_if_needed("dont_come", obj)
    # Fallback shim object so tests can run without the engine.
    class _Shim:
        def __init__(self, kind, number, amount):
            self.kind = _norm(kind)
            self.number = number
            self.amount = int(amount)
            self.working = True
            self.odds_amount = 0    # pass/come odds
            self.lay_odds = 0       # dp/dc lay odds
    return _Shim(k, number, amount)

def _find_existing(player, kind: str, number: Optional[int]):
    bets = getattr(player, "bets", None)
    if not bets:
        return None
    target = _norm(kind)
    for b in list(bets):
        if _bet_kind(b) != target:
            continue
        if target == "place" and number is not None and _bet_number(b) != number:
            continue
        return b
    return None

def _iter_bets(player, kind: str):
    bets = getattr(player, "bets", None)
    if not bets:
        return []
    target = _norm(kind)
    return [b for b in list(bets) if _bet_kind(b) == target]

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

    if "odds" in meta:
        table = getattr(player, "table", None)
        point = getattr(table, "point_number", None) if table else None
        bubble = bool(getattr(table, "bubble", False)) if table else False
        base_flat = int(getattr(bet_obj, "amount", 0))
        policy = odds_policy if odds_policy is not None else "3-4-5x"

        k = _norm(kind)
        if k == "pass":
            legalized = legalize_odds(point, int(meta["odds"]), base_flat, bubble=bubble, policy=policy)
            if not _set_odds_known_attrs(bet_obj, legalized):
                _force_sidecar_odds(bet_obj, "pass", legalized)
        elif k == "dont_pass":
            legalized = legalize_lay_odds(point, int(meta["odds"]), base_flat, bubble=bubble, policy=policy)
            if not _set_odds_known_attrs(bet_obj, legalized):
                _force_sidecar_odds(bet_obj, "dont_pass", legalized)
            _mirror_lay_and_amount(bet_obj, legalized)

def _apply_odds_to_existing(player, kind: str, desired_odds: int, scope: str, odds_policy: str | int | None):
    """
    Apply odds to existing Come / Don't Come bets based on their current numbers.
    - kind: 'come' | 'dont_come'
    - scope: 'all' | 'newest'
    """
    bets = _iter_bets(player, kind)
    if not bets:
        return

    targets = bets if scope == "all" else [bets[-1]]

    table = getattr(player, "table", None)
    bubble = bool(getattr(table, "bubble", False)) if table else False
    policy = odds_policy if odds_policy is not None else "3-4-5x"

    for b in targets:
        point = _bet_number(b)
        if point not in (4, 5, 6, 8, 9, 10):  # no odds until moved
            continue
        base_flat = int(getattr(b, "amount", 0))
        k = _norm(kind)
        if k == "come":
            legalized = legalize_odds(point, int(desired_odds), base_flat, bubble=bubble, policy=policy)
            if not _set_odds_known_attrs(b, legalized):
                _force_sidecar_odds(b, "come", legalized)
        elif k == "dont_come":
            legalized = legalize_lay_odds(point, int(desired_odds), base_flat, bubble=bubble, policy=policy)
            if not _set_odds_known_attrs(b, legalized):
                _force_sidecar_odds(b, "dont_come", legalized)
            _mirror_lay_and_amount(b, legalized)

def apply_intents(player, intents: List[BetIntent], *, odds_policy: str | int | None = None):
    """
    Apply a list of bet intents onto the player.
    - If a __clear__ sentinel is present, clear first, then apply others.
    - Apply __apply_odds__ intents up-front (they affect existing bets).
    """
    if not intents:
        return

    # Clear first if present
    if any(k == "__clear__" for (k, *rest) in intents):
        _clear_all_bets(player)
        intents = [t for t in intents if t[0] != "__clear__"]

    # Apply-odds control intents
    control_intents = [t for t in intents if t[0] == "__apply_odds__"]
    for _, kind, amt, meta in control_intents:
        scope = (meta or {}).get("scope", "all")
        _apply_odds_to_existing(player, str(kind), int(amt), str(scope), odds_policy)

    # Normal upsert intents
    for item in intents:
        if item[0] == "__apply_odds__":
            continue  # already handled

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