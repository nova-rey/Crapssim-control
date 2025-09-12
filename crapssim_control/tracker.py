# tracker.py

from __future__ import annotations
from typing import Dict, Optional


class Tracker:
    """
    Lightweight, test-friendly tracker for a craps session.
    Exposes small event handlers and a stable snapshot() structure.
    """

    _INSIDE = {5, 6, 8, 9}
    _CRAPS = {2, 3, 12}
    _NATURALS = {7, 11}

    def __init__(self, cfg: Optional[dict] = None) -> None:
        cfg = cfg or {}
        self._enabled: bool = bool(cfg.get("enabled", True))

        # Point state
        self._point: int = 0  # 0 == off

        # Roll state
        self._roll: Dict[str, int | Optional[int]] = {
            "last_roll": None,       # type: ignore[typeddict-item]
            "shooter_rolls": 0,
            "rolls_since_point": 0,
            "comeout_rolls": 0,
            "comeout_naturals": 0,
            "comeout_craps": 0,
        }

        # Overall hit histogram (all rolls counted; tests read specific numbers)
        self._hits: Dict[int, int] = {}

        # Per-point-cycle stats (reset on point establish/made/seven-out)
        self._since_point = {
            "inside_hits": 0,
            "outside_hits": 0,
            "hits": {},  # per-number histogram for the current point cycle
        }

        # Bankroll, peak, drawdown, and per-point-cycle PnL
        self._bankroll: float = 0.0
        self._bankroll_peak: float = 0.0
        self._drawdown: float = 0.0
        self._pnl_since_point: float = 0.0

        # Session-level tallies
        self._session = {
            "seven_outs": 0,
            "pso": 0,  # point–seven-out (exactly one roll occurred after point came on)
        }

    # --------------------------
    # Helpers
    # --------------------------

    def _reset_point_cycle(self) -> None:
        """Reset counters that are scoped to a single point cycle."""
        self._roll["rolls_since_point"] = 0
        self._pnl_since_point = 0.0
        self._since_point = {
            "inside_hits": 0,
            "outside_hits": 0,
            "hits": {},
        }

    def _bump_hist(self, hist: Dict[int, int], n: int) -> None:
        hist[n] = hist.get(n, 0) + 1

    # --------------------------
    # Public API (event handlers)
    # --------------------------

    def on_roll(self, n: int) -> None:
        """
        Called on every dice roll.
        - Tracks comeout counters when point is off.
        - Tracks hits, shooter count, rolls since point when point is on.
        """
        if not self._enabled:
            return

        self._roll["last_roll"] = n
        self._roll["shooter_rolls"] += 1
        self._bump_hist(self._hits, n)

        if self._point == 0:
            # Comeout roll
            self._roll["comeout_rolls"] += 1
            if n in self._NATURALS:
                self._roll["comeout_naturals"] += 1
            elif n in self._CRAPS:
                self._roll["comeout_craps"] += 1
            # No rolls_since_point changes while point is off
            return

        # Point is on → count towards point cycle
        self._roll["rolls_since_point"] += 1
        self._bump_hist(self._since_point["hits"], n)

        if n in self._INSIDE:
            self._since_point["inside_hits"] += 1
        elif n != 7:  # treat non-inside (except 7) as outside for simple tracking
            self._since_point["outside_hits"] += 1

    def on_point_established(self, point: int) -> None:
        """Point turns on to the specified number and resets point-cycle counters."""
        if not self._enabled:
            return
        self._point = point
        self._reset_point_cycle()

    def on_point_made(self) -> None:
        """
        The shooter made the point (did not seven out).
        Reset the point cycle and turn the point off, but keep the same shooter.
        """
        if not self._enabled:
            return
        # Turn point off and reset per-cycle counters.
        self._point = 0
        self._reset_point_cycle()
        # shooter_rolls intentionally NOT reset (same shooter continues)

    def on_seven_out(self) -> None:
        """
        Shooter sevened out. Increments session counters and resets for a new shooter.
        PSO is when exactly ONE roll occurred after the point turned on.
        """
        if not self._enabled:
            return

        is_pso = bool(self._point and self._roll["rolls_since_point"] == 1)
        self._session["seven_outs"] += 1
        if is_pso:
            self._session["pso"] += 1

        # Turn off point and reset point-cycle stats
        self._point = 0
        self._reset_point_cycle()

        # New shooter
        self._roll["shooter_rolls"] = 0

    def on_bankroll_delta(self, amount: float) -> None:
        """
        Apply a bankroll delta (win/loss). Updates peak, drawdown,
        and attributes the amount to the current point cycle PnL.
        """
        if not self._enabled:
            return

        self._bankroll += float(amount)
        if self._bankroll > self._bankroll_peak:
            self._bankroll_peak = self._bankroll
        # drawdown is how far below peak we are (never negative)
        self._drawdown = max(0.0, self._bankroll_peak - self._bankroll)

        # Attribute to current point cycle
        self._pnl_since_point += float(amount)

    # --------------------------
    # Introspection
    # --------------------------

    def snapshot(self) -> dict:
        """Return a read-only snapshot used by tests/consumers."""
        return {
            "roll": {
                "last_roll": self._roll["last_roll"],
                "shooter_rolls": self._roll["shooter_rolls"],
                "rolls_since_point": self._roll["rolls_since_point"],
                "comeout_rolls": self._roll["comeout_rolls"],
                "comeout_naturals": self._roll["comeout_naturals"],
                "comeout_craps": self._roll["comeout_craps"],
            },
            "point": {
                "point": self._point if self._point else 0,
            },
            "hits": dict(self._hits),
            "since_point": {
                "inside_hits": self._since_point["inside_hits"],
                "outside_hits": self._since_point["outside_hits"],
                "hits": dict(self._since_point["hits"]),
            },
            "bankroll": {
                "bankroll": self._bankroll,
                "bankroll_peak": self._bankroll_peak,
                "drawdown": self._drawdown,
                "pnl_since_point": self._pnl_since_point,
            },
            "session": {
                "seven_outs": self._session["seven_outs"],
                "pso": self._session["pso"],
            },
        }