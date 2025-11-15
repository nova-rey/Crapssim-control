"""Engine adapter protocol definitions for CSC."""

from __future__ import annotations

from typing import Any, Dict, Protocol, Tuple, runtime_checkable

EngineStateDict = Dict[str, Any]


@runtime_checkable
class EngineAdapter(Protocol):
    """Protocol shared by engine adapters consumed by CSC runtime."""

    def start_session(self, spec: Dict[str, Any], seed: int | None = None) -> None:
        """Start or reset the underlying engine session."""

    def step_roll(self, dice: Tuple[int, int] | None = None) -> EngineStateDict:
        """Advance the engine by one roll."""

    def apply_action(self, verb: str, args: Dict[str, Any]) -> EngineStateDict:
        """Apply a CSC verb/action to the engine."""

    def snapshot_state(self) -> EngineStateDict:
        """Return the most recent engine snapshot."""
