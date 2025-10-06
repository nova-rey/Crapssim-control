"""
engine_adapter.py — CrapsSim-Control ↔ CrapsSim bridge

- Prefers modern CrapsSim (≥0.3.x) Strategy API (crapssim.strategy)
- Graceful fallback to legacy Players API (crapssim.players) if present
- Attaches with keyword (strategy=...) to avoid bankroll positional mixups
- ControlStrategy implements update_bets(self, player) and mutates the player
  with a minimal Iron Cross (Pass Line on comeout; Place 6/8 + Field when point is ON)
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List, TYPE_CHECKING

# --- Detect CrapsSim shape ----------------------------------------------------

_HAS_LEGACY_PLAYERS = False
try:
    import crapssim.strategy as cs_strategy  # modern
except ModuleNotFoundError:
    cs_strategy = None  # type: ignore

try:
    import crapssim.players as cs_players  # legacy (older CrapsSim)
    _HAS_LEGACY_PLAYERS = True
except ModuleNotFoundError:
    cs_players = None  # type: ignore

# Table is optional at import time; only fail when we actually attach.
try:
    from crapssim.table import Table as _CsTable  # runtime alias
except Exception:
    _CsTable = None  # type: ignore

if TYPE_CHECKING:  # for type checkers/IDEs only
    from crapssim.table import Table  # noqa: F401


# --- Public adapter surface used by the CLI -----------------------------------

@dataclass
class EngineAttachResult:
    table: Any
    controller_player: Any
    meta: Dict[str, Any]


def _resolve_modern_strategy_base() -> Tuple[Optional[type], Optional[type]]:
    """Probe for modern Strategy base class name differences."""
    if cs_strategy is None:
        return None, None
    StrategyBase = getattr(cs_strategy, "Strategy", None) or getattr(cs_strategy, "BaseStrategy", None)
    SimplePass = getattr(cs_strategy, "PassLineStrategy", None)
    return StrategyBase, SimplePass


# --------------------------- ControlStrategy (CSC) ----------------------------

def _build_controller_strategy(spec: Dict[str, Any], strategy_base: type) -> Any:
    """
    Strategy that MUTATES the provided player in update_bets(player).

    Iron Cross (minimal):
      - Comeout: Pass Line $10
      - Point ON: Place 6 & 8 for $12 each + $5 Field
    """
    import crapssim.bet as B
    PassLine = getattr(B, "PassLine", None)
    Place = getattr(B, "Place", None)
    Field = getattr(B, "Field", None)

    def _point_value(table):
        pt = getattr(table, "point", None)
        if pt is not None and not isinstance(pt, (int, type(None))):
            pt = getattr(pt, "value", getattr(pt, "number", None))
        return pt

    # Simple constructors (NO player arg — your Player.add_bet binds ownership)
    def _mk_pass(amount: int):
        if not PassLine:
            return None
        try:
            return PassLine(amount=amount)
        except TypeError:
            try:
                return PassLine(amount)
            except Exception:
                return None

    def _mk_field(amount: int):
        if not Field:
            return None
        try:
            return Field(amount=amount)
        except TypeError:
            try:
                return Field(amount)
            except Exception:
                return None

    def _mk_place(number: int, amount: int):
        if not Place:
            return None
        # try kwargs then positional
        for kw in ({"number": number, "amount": amount},
                   {"amount": amount, "number": number}):
            try:
                return Place(**kw)
            except TypeError:
                pass
        for args in ((number, amount),):
            try:
                return Place(*args)
            except Exception:
                pass
        return None

    class ControlStrategy(strategy_base):  # type: ignore[misc]
        def __init__(self, spec_dict: Dict[str, Any]):
            try:
                super().__init__()
            except TypeError:
                try:
                    super().__init__(name="CSC-Control")
                except TypeError:
                    pass
            self.name = "CSC-Control"
            self._spec = spec_dict
            self._armed = False
            self._last_point = None

        # ---------- tolerant helpers over player API ----------
        def _player_add_many(self, player, bets: List[Any]) -> bool:
            bets = [b for b in bets if b is not None]
            if not bets:
                return False
            fn = getattr(player, "add_strategy_bets", None)
            if callable(fn):
                try:
                    fn(bets)
                    return True
                except Exception:
                    pass
            ok = False
            add1 = getattr(player, "add_bet", None)
            if callable(add1):
                for b in bets:
                    try:
                        add1(b)
                        ok = True
                    except Exception:
                        pass
                if ok:
                    return True
            # last resort: append to public list if present
            try:
                lst = getattr(player, "bets", None)
                if isinstance(lst, list):
                    lst.extend(b for b in bets if b is not None)
                    return True
            except Exception:
                pass
            return False

        def _player_clear_bets(self, player) -> bool:
            for name in ("clear_bets", "clear", "reset_bets"):
                fn = getattr(player, name, None)
                if callable(fn):
                    try:
                        fn()
                        return True
                    except Exception:
                        continue
            try:
                bets = getattr(player, "bets", None)
                if isinstance(bets, list):
                    bets[:] = []
                    return True
            except Exception:
                pass
            return False

        # ============= REQUIRED by Strategy ABC =================
        # signature must be (self, player) -> None
        def update_bets(self, player) -> None:
            table = getattr(player, "table", None)
            point = _point_value(table) if table is not None else None
            comeout = point in (None, 0)

            # reset state on comeout/new point
            if comeout or point != self._last_point:
                self._armed = False
                self._last_point = point
                self._player_clear_bets(player)

            if comeout:
                # Pass Line $10
                self._player_add_many(player, [_mk_pass(10)])
                return

            # Point is ON
            if not self._armed:
                # Place 6 & 8 for $12; Field $5
                self._player_add_many(player, [
                    _mk_place(6, 12),
                    _mk_place(8, 12),
                    _mk_field(5),
                ])
                self._armed = True

        def completed(self, player) -> bool:
            return False

        # optional hooks
        def reset(self, *a, **k):
            self._armed, self._last_point = False, None

        def on_shooter_change(self, *a, **k):
            self.reset()

        def on_comeout(self, *a, **k):
            return

        def on_point_established(self, *a, **k):
            return

        def on_point(self, *a, **k):
            return

        def on_roll(self, *a, **k):
            return

        def on_seven_out(self, *a, **k):
            self.reset()

        def apply_template(self, *a, **k):
            return

        def clear_bets(self, *a, **k):
            return

    # Make sure any extra abstract names are stubbed
    abstract = getattr(strategy_base, "__abstractmethods__", set()) or set()
    for name in abstract:
        if not hasattr(ControlStrategy, name):
            setattr(
                ControlStrategy,
                name,
                (lambda *a, **k: False) if name == "completed" else (lambda *a, **k: None),
            )

    return ControlStrategy(spec)


# ------------------------------- Attach paths --------------------------------

def _attach_modern(table: Any, spec: Dict[str, Any]) -> EngineAttachResult:
    StrategyBase, _ = _resolve_modern_strategy_base()
    if StrategyBase is None:
        raise RuntimeError(
            "CrapsSim ≥0.3.x detected but no Strategy base found. "
            "Expected crapssim.strategy.Strategy or .BaseStrategy."
        )

    controller_strategy = _build_controller_strategy(spec, StrategyBase)

    # Choose a bankroll (spec override -> run -> table -> default)
    bankroll = int(
        spec.get("bankroll")
        or spec.get("run", {}).get("bankroll")
        or spec.get("table", {}).get("bankroll", 1000)
    )

    # Attach strategy (use whatever the table exposes)
    add_player = getattr(table, "add_player", None)
    add_strategy = getattr(table, "add_strategy", None)

    if callable(add_player):
        # Try to attach with keywords (some builds ignore bankroll here)
        attached = False
        for kw_name in ("strategy", "bet_strategy"):
            try:
                add_player(bankroll=bankroll, **{kw_name: controller_strategy}, name="CSC-Control")
                attached = True
                break
            except TypeError:
                continue
        if not attached:
            try:
                add_player(bankroll=bankroll, strategy=controller_strategy)
                attached = True
            except Exception:
                try:
                    add_player(bankroll=bankroll, bet_strategy=controller_strategy)
                    attached = True
                except Exception:
                    # LAST resort: positional (may be ignored by some builds)
                    add_player(bankroll, controller_strategy, "CSC-Control")
                    attached = True
    elif callable(add_strategy):
        try:
            add_strategy(strategy=controller_strategy, name="CSC-Control")
        except TypeError:
            add_strategy(strategy=controller_strategy)
    else:
        raise RuntimeError("Table has neither add_player nor add_strategy.")

    # --- Force bankroll on the attached player (engines that ignore kwargs) ---
    try:
        players = getattr(table, "players", None)
        p0 = players[0] if players else None
        if p0 is None:
            raise RuntimeError("No player attached after add_* call.")

        # Try setter first
        set_br = getattr(p0, "set_bankroll", None)
        if callable(set_br):
            set_br(float(bankroll))
        else:
            # Set all plausible attributes
            for attr in ("bankroll", "total_player_cash", "chips", "_bankroll"):
                if hasattr(p0, attr):
                    try:
                        setattr(p0, attr, float(bankroll))
                    except Exception:
                        pass
    except Exception:
        # Non-fatal
        pass

    return EngineAttachResult(
        table=table,
        controller_player=controller_strategy,
        meta={"mode": "modern", "bankroll": bankroll},
    )


def _attach_legacy(table: Any, spec: Dict[str, Any]) -> EngineAttachResult:
    """Fallback for older CrapsSim exposing crapssim.players."""
    if cs_players is None:
        raise RuntimeError("Legacy players API requested but 'crapssim.players' is unavailable.")

    BasePlayer = getattr(cs_players, "BasePlayer", None) or getattr(cs_players, "Player", None)
    if BasePlayer is None:
        raise RuntimeError("Could not find BasePlayer/Player in crapssim.players.")

    class ControlPlayer(BasePlayer):  # type: ignore[misc]
        def __init__(self, spec_dict: Dict[str, Any]):
            super().__init__()
            self._spec = spec_dict
            self._state: Dict[str, Any] = {"mode": spec_dict.get("start_mode", "default")}

        def on_comeout(self, table):
            return

        def on_point(self, table, point):
            return

        def on_roll(self, table, roll):
            return

        def on_seven_out(self, table):
            return

        def apply_template(self, table, template: Dict[str, Any]):
            return

        def clear_bets(self, table):
            return

    p = ControlPlayer(spec)
    table.add_player(p)
    return EngineAttachResult(table=table, controller_player=p, meta={"mode": "legacy"})


def attach_engine(spec: Dict[str, Any]) -> EngineAttachResult:
    """
    Prepare a Table and attach our control object.
    Prefer modern Strategy path; fall back to legacy players if available.
    """
    if _CsTable is None and cs_strategy is None and not _HAS_LEGACY_PLAYERS:
        raise RuntimeError(
            "Could not attach to CrapsSim: engine not installed (no 'crapssim')."
        )

    if _CsTable is not None:
        t = _CsTable()
    else:
        class _ShimTable:
            def __init__(self): self.players = []
            def add_player(self, *a, **k): self.players.append(object())
            def add_strategy(self, *a, **k): pass
        t = _ShimTable()

    if cs_strategy is not None:
        return _attach_modern(t, spec)
    if _HAS_LEGACY_PLAYERS:
        return _attach_legacy(t, spec)
    raise RuntimeError(
        "Could not attach to CrapsSim. "
        "Neither 'crapssim.strategy' (modern) nor 'crapssim.players' (legacy) is available."
    )


# --- Compatibility shim for older CLI expecting EngineAdapter -----------------

class EngineAdapter:
    """
    Back-compat wrapper expected by the CLI.
    Provides .attach(spec) and a classmethod attach as well.
    """
    def __init__(self, *args, **kwargs):
        # Newer adapter no longer needs table/player injected here
        pass

    def attach(self, spec: Dict[str, Any]) -> EngineAttachResult:
        return attach_engine(spec)

    @classmethod
    def attach_cls(cls, spec: Dict[str, Any]) -> EngineAttachResult:
        return attach_engine(spec)


# Keep a direct name too, just in case someone imports the function
attach = attach_engine  # type: ignore
__all__ = ["EngineAttachResult", "EngineAdapter", "attach_engine", "attach"]
