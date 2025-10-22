"""
transport.py — Abstract EngineTransport and LocalTransport implementation.

Provides a unified interface for CSC to communicate with CrapsSim or future API engines.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple
import importlib


class EngineTransport(ABC):
    """Abstract transport layer between CSC and a craps engine."""

    @abstractmethod
    def start_session(self, spec: Dict[str, Any]) -> None:
        """Initialize a new simulation session."""
        raise NotImplementedError

    @abstractmethod
    def apply(self, verb: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a betting verb/action through the engine."""
        raise NotImplementedError

    @abstractmethod
    def step(
        self, dice: Optional[Tuple[int, int]] = None, seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """Advance one roll."""
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> Dict[str, Any]:
        """Return a normalized snapshot from the engine."""
        raise NotImplementedError

    @abstractmethod
    def version(self) -> Dict[str, Any]:
        """Return engine identity and version info."""
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        """Return engine capabilities if available."""
        raise NotImplementedError


class LocalTransport(EngineTransport):
    """Local in-process CrapsSim transport used by default."""

    def __init__(self) -> None:
        self._engine = None
        self._table = None
        self._player = None
        self._spec: Dict[str, Any] = {}

    def start_session(self, spec: Dict[str, Any]) -> None:
        """Create a CrapsSim table and attach CSC control player/strategy."""
        self._spec = spec
        try:
            cs_table_mod = importlib.import_module("crapssim.table")
            Table = getattr(cs_table_mod, "Table", None)
            self._table = Table() if Table else None
        except Exception:
            self._table = None

    def apply(self, verb: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a bet or command to the engine. Currently stubbed; delegates to adapter logic."""
        # For now, we only simulate a basic acknowledgment.
        return {"verb": verb, "args": args, "status": "ok"}

    def step(
        self, dice: Optional[Tuple[int, int]] = None, seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """Simulate one roll step."""
        return {"result": "noop", "dice": dice, "seed": seed}

    def snapshot(self) -> Dict[str, Any]:
        """Return stubbed engine state for now."""
        return {
            "bankroll": 0.0,
            "point_on": False,
            "point_value": None,
            "bets": {},
            "hand_id": 0,
            "roll_in_hand": 0,
            "rng_seed": 0,
        }

    def version(self) -> Dict[str, Any]:
        """Return static CrapsSim identity (if available)."""
        try:
            cs = importlib.import_module("crapssim")
            ver = getattr(cs, "__version__", "unknown")
        except Exception:
            ver = "unavailable"
        return {"engine": "crapssim", "version": ver}

    def capabilities(self) -> Dict[str, Any]:
        """Return basic detected capabilities (empty for vanilla)."""
        try:
            import crapssim.bet as cs_bet

            return {"detected": sorted([x for x in dir(cs_bet) if x[0].isupper()])}
        except Exception:
            return {}
