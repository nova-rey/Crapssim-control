"""Helpers for replay parity and performance sanity checks."""

from __future__ import annotations

import time
from typing import List, Tuple

from crapssim_control.engine_adapter import VanillaAdapter


def run_replay_parity(seed: int = 42, rolls: int = 200) -> bool:
    live = VanillaAdapter()
    live.start_session({"seed": seed})
    dice_seq: List[Tuple[int, int]] = []
    live_snapshots = []
    for _ in range(rolls):
        result = live.step_roll()
        dice = result.get("dice", (0, 0))
        if isinstance(dice, (tuple, list)):
            try:
                die_a = int(dice[0])
                die_b = int(dice[1])
            except Exception:
                die_a, die_b = 0, 0
        else:
            die_a, die_b = 0, 0
        dice_seq.append((die_a, die_b))
        live_snapshots.append(live.snapshot_state())

    replay = VanillaAdapter()
    replay.start_session({"seed": seed})
    replay_snaps = []
    for dice in dice_seq:
        replay.step_roll(dice=dice)
        replay_snaps.append(replay.snapshot_state())

    digest_live = sum(float(s.get("bankroll", 0)) for s in live_snapshots)
    digest_replay = sum(float(s.get("bankroll", 0)) for s in replay_snaps)
    return abs(digest_live - digest_replay) < 1e-6


def run_perf_test(rolls: int = 5000, seed: int = 42):
    adapter = VanillaAdapter()
    adapter.start_session({"seed": seed})
    t0 = time.perf_counter()
    for _ in range(rolls):
        adapter.step_roll()
    elapsed = time.perf_counter() - t0
    rps = rolls / elapsed if elapsed > 0 else float("inf")
    return {"rolls": rolls, "elapsed": elapsed, "rps": rps}
