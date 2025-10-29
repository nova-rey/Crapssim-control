"""Helpers for Phase 6 baseline capture scripts."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class BaselineEvent:
    """Represents a normalized craps event used for baseline playback."""

    data: Dict[str, object]

    def as_dict(self) -> Dict[str, object]:
        return dict(self.data)


def generate_event_sequence(
    seed: int,
    *,
    shooters: int = 7,
    rolls_per_shooter: int = 6,
    starting_bankroll: float = 1000.0,
) -> List[BaselineEvent]:
    """Generate a deterministic sequence of craps events.

    The sequence is intentionally synthetic but stable.  It drives the controller's
    analytics pipeline, emits webhook payloads for Node-RED, and exercises the
    external command channel limits once the bankroll dips under the configured
    threshold.
    """

    rng = random.Random(seed)
    bankroll = float(starting_bankroll)
    events: List[BaselineEvent] = []
    hand_id = 0
    trigger_indices = {0}
    trigger_indices.update({1 + i * 2 for i in range(15)})
    trigger_budget = len(trigger_indices)

    for shooter_index in range(max(1, shooters)):
        hand_id += 1

        events.append(
            BaselineEvent(
                {
                    "type": "comeout",
                    "hand_id": hand_id,
                    "roll_in_hand": 0,
                    "bankroll_before": bankroll,
                    "bankroll_after": bankroll,
                    "point": None,
                    "point_on": False,
                    "shooter": shooter_index + 1,
                }
            )
        )

        point = rng.choice([4, 5, 6, 8, 9])
        bankroll_before_point = bankroll
        bankroll -= 10.0
        events.append(
            BaselineEvent(
                {
                    "type": "point_established",
                    "hand_id": hand_id,
                    "roll_in_hand": 0,
                    "point": point,
                    "point_on": True,
                    "bankroll_before": bankroll_before_point,
                    "bankroll_after": bankroll,
                    "shooter": shooter_index + 1,
                }
            )
        )

        roll_in_hand = 0
        for _ in range(max(1, rolls_per_shooter)):
            roll_in_hand += 1
            total = rng.randint(3, 11)
            die_one = rng.randint(1, 6)
            die_two = max(1, min(6, total - die_one))

            global_roll = shooter_index * max(1, rolls_per_shooter) + (roll_in_hand - 1)
            if global_roll in trigger_indices and trigger_budget > 0:
                trigger_budget -= 1
                drop = rng.choice([105, 120, 135])
                candidate = bankroll - drop
                if candidate >= 890:
                    candidate = bankroll - (drop + 35)
                candidate = max(520.0, min(880.0, candidate))
            else:
                bump = rng.choice([24, 30, 36])
                candidate = bankroll + bump
                if candidate < 915:
                    candidate += 28
                candidate = max(520.0, min(1080.0, candidate))
            previous = bankroll
            bankroll = max(420.0, min(1150.0, candidate))

            payload = {
                "type": "roll",
                "hand_id": hand_id,
                "roll_in_hand": roll_in_hand,
                "point": point,
                "point_on": True,
                "bankroll_before": previous,
                "bankroll_after": bankroll,
                "event_total": total,
                "roll": total,
                "dice": [die_one, die_two],
            }
            if shooter_index == 0 and roll_in_hand == 1:
                payload["resolving"] = True

            events.append(BaselineEvent(payload))

        seven_before = bankroll
        bankroll = max(400.0, bankroll - rng.choice([12.0, 18.0, 24.0]))
        events.append(
            BaselineEvent(
                {
                    "type": "seven_out",
                    "hand_id": hand_id,
                    "roll_in_hand": roll_in_hand,
                    "point": point,
                    "point_on": False,
                    "bankroll_before": seven_before,
                    "bankroll_after": bankroll,
                    "shooter": shooter_index + 1,
                }
            )
        )

    return events


def iter_event_dicts(events: Iterable[BaselineEvent]) -> Iterable[Dict[str, object]]:
    for event in events:
        yield event.as_dict()
