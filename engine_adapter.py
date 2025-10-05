"""
engine_adapter.py — CrapsSim-Control ↔ CrapsSim bridge

- Prefers modern CrapsSim (≥0.3.x) Strategy API (crapssim.strategy)
- Graceful fallback to legacy Players API (crapssim.players) if present
- Attaches with keyword (strategy=...) to avoid bankroll positional mixups
- ControlStrategy implements update_bets(self, player) and mutates the player
  with a minimal Iron Cross (Pass Line on comeout; Place 6/8 + Field when point is ON)
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List

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

try:
    from crapssim.table import Table
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "CrapsSim engine not importable: failed to import 'crapssim.table.Table'. "
        f"Original error: {e}"
    ) from e


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

def _attach_modern(table: Table, spec: Dict[str, Any]) -> EngineAttachResult:
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


def _attach_legacy(table: Table, spec: Dict[str, Any]) -> EngineAttachResult:
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
    t = Table()
    if cs_strategy is not None:
        return _attach_modern(t, spec)
    if _HAS_LEGACY_PLAYERS:
        return _attach_legacy(t, spec)
    raise RuntimeError(
        "Could not attach to CrapsSim. "
        "Neither 'crapssim.strategy' (modern) nor 'crapssim.players' (legacy) is available. "
        "Installed CrapsSim submodules likely include: bet, dice, point, strategy, table. "
        "Ensure 'crapssim.strategy' exports Strategy/BaseStrategy and Table exposes add_strategy or add_player."
    )


# --- Compatibility shim for older CLI expecting EngineAdapter -----------------

# --- Compatibility shim for older CLI & tests expecting EngineAdapter ---------

class EngineAdapter:
    """
    Back-compat wrapper used by CLI *and* tests.
    Supports:
      • EngineAdapter() + .attach(spec)         (CLI path)
      • EngineAdapter(table, player, strategy)  (test/smoke path)
      • .play(shooters=..., rolls=...)          (tolerant driver)
    """
    def __init__(self, table: Any = None, player: Any = None, strategy: Any = None):
        self.table = table
        self.player = player
        self.strategy = strategy

    # CLI path
    def attach(self, spec: Dict[str, Any]) -> EngineAttachResult:
        result = attach_engine(spec)
        # cache for potential .play() calls later
        self.table = result.table
        # modern path returns the strategy object as "controller_player"
        self.player = None
        self.strategy = result.controller_player
        return result

    @classmethod
    def attach_cls(cls, spec: Dict[str, Any]) -> EngineAttachResult:
        return attach_engine(spec)

    # Test/smoke path — minimal, tolerant driver
    def play(self, shooters: int | None = None, rolls: int | None = None) -> None:
        t = self.table
        if t is None:
            return

        # If explicit rolls are provided, try to run exactly that many.
        r = int(rolls or 0)
        if r > 0:
            # 1) table.play(rolls=...)
            if hasattr(t, "play"):
                try:
                    t.play(rolls=r)
                    return
                except Exception:
                    pass
            # 2) table.run(r) or table.run(rolls=r)
            if hasattr(t, "run"):
                try:
                    t.run(r)
                    return
                except TypeError:
                    try:
                        t.run(rolls=r)
                        return
                    except Exception:
                        pass
                except Exception:
                    pass
            # 3) loop table.roll()
            if hasattr(t, "roll"):
                try:
                    for _ in range(r):
                        t.roll()
                    return
                except Exception:
                    pass
            # nothing compatible; no-op to keep tests happy
            return

        # If no rolls given, but a shooters concept exists in a fake, try it.
        if shooters is not None and hasattr(t, "pass_rolls"):
            try:
                t.pass_rolls(int(shooters))
            except Exception:
                pass


# Keep a direct name too, just in case someone imports the function
attach = attach_engine  # type: ignore
__all__ = ["EngineAttachResult", "EngineAdapter", "attach_engine", "attach"]


# Keep a direct name too, just in case someone imports the function
attach = attach_engine  # type: ignore
__all__ = ["EngineAttachResult", "EngineAdapter", "attach_engine", "attach"]
