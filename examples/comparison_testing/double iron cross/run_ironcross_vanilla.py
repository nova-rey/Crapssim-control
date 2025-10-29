#!/usr/bin/env python3
"""
Run CrapsSim's built-in IronCross strategy with a fixed seed,
so you can compare against a CSC spec using the same seed.

Usage:
  python examples/run_ironcross_vanilla.py --rolls 200 --seed 42
"""
from __future__ import annotations

import argparse
import random

from crapssim.dice import Dice
from crapssim.player import Player
from crapssim.strategy.examples import IronCross
from crapssim.table import Table


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rolls", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--bubble", action="store_true", help="Bubble table (no dealer)")
    ap.add_argument("--level", type=int, default=10, help="Table min / base level")
    args = ap.parse_args()

    # Fixed seed for deterministic comparison
    random.seed(args.seed)
    dice = Dice(seed=args.seed)

    table = Table(bubble=args.bubble, level=args.level, dice=dice)
    player = Player(name="IronCrossVanilla")

    # Use CrapsSim's example strategy directly
    strat = IronCross(pass_amount=5.0, field_amount=5.0, place5=10.0, place6=12.0, place8=12.0)
    table.add_player(player)
    table.add_strategy(player, strat)

    # Play
    table.play(args.rolls)

    # Print a simple summary compatible with what we do in CSC
    bankroll = getattr(player, "bankroll", None)
    if bankroll is not None:
        print(f"RESULT: rolls={args.rolls} bankroll={bankroll:.2f}")
    else:
        print(f"RESULT: rolls={args.rolls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
