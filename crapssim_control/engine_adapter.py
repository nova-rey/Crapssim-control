from __future__ import annotations
from abc import ABC, abstractmethod
import warnings
from typing import Any, Dict, Tuple, Optional


class EngineAdapter(ABC):
    """Abstract base adapter defining the CrapsSim engine interface."""

    @abstractmethod
    def start_session(self, spec: Dict[str, Any]) -> None:
        """Initialize the engine with a simulation spec."""
        raise NotImplementedError

    @abstractmethod
    def step_roll(self, dice: Optional[Tuple[int, int]] = None, seed: Optional[int] = None) -> Dict[str, Any]:
        """Advance one roll using fixed dice or RNG seed."""
        raise NotImplementedError

    @abstractmethod
    def apply_action(self, verb: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a CSC action to the engine and return the effect."""
        raise NotImplementedError

    @abstractmethod
    def snapshot_state(self) -> Dict[str, Any]:
        """Return a snapshot of current engine state."""
        raise NotImplementedError


class NullAdapter(EngineAdapter):
    """No-op adapter used when no engine is available."""

    def start_session(self, spec: Dict[str, Any]) -> None:
        return None

    def step_roll(self, dice: Optional[Tuple[int, int]] = None, seed: Optional[int] = None) -> Dict[str, Any]:
        return {"result": "noop", "dice": dice, "seed": seed}

    def apply_action(self, verb: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"applied": verb, "args": args, "result": "noop"}

    def snapshot_state(self) -> Dict[str, Any]:
        return {
            "bankroll": 0.0,
            "point_on": False,
            "point_value": None,
            "bets": {},
            "hand_id": 0,
            "roll_in_hand": 0,
            "rng_seed": 0,
        }

    # --- Back-compat shims (TEMP: remove by P7·C3) ---
    import warnings

    def attach(self, spec: Dict[str, Any]):
        """Legacy shim: alias to start_session(spec)."""
        warnings.warn(
            "NullAdapter.attach() is deprecated; use start_session(). Will be removed in P7·C3.",
            DeprecationWarning,
        )
        self.start_session(spec)
        return {"attached": True, "mode": "noop"}

    @classmethod
    def attach_cls(cls, spec: Dict[str, Any]):
        """Legacy shim: mirrors prior classmethod attach API."""
        warnings.warn(
            "NullAdapter.attach_cls() is deprecated; use start_session() on an instance. Will be removed in P7·C3.",
            DeprecationWarning,
        )
        inst = cls()
        return inst.attach(spec)

    def play(self, shooters: int = 1, rolls: int = 3) -> Dict[str, Any]:
        """Legacy smoke-runner shim; does not require an engine."""
        warnings.warn(
            "NullAdapter.play() is deprecated; use controller-run paths. Will be removed in P7·C3.",
            DeprecationWarning,
        )
        return {"shooters": int(shooters), "rolls": int(rolls), "status": "noop"}
