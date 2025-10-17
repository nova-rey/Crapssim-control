"""Context dataclasses for analytics scaffolding."""

from dataclasses import dataclass


@dataclass
class SessionCtx:
    bankroll: float


@dataclass
class HandCtx:
    hand_id: int
    point: int | None = None


@dataclass
class RollCtx:
    hand_id: int
    roll_number: int
    bankroll_before: float
    delta: float
