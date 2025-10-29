# run_demo.py
import inspect
import sys
from pathlib import Path

import numpy as np
from typing import List, Tuple

try:
    from crapssim.table import Table
except Exception as e:
    Table = None  # type: ignore[assignment]
    _ENGINE_IMPORT_ERROR = e
else:
    _ENGINE_IMPORT_ERROR = None

from crapssim_control import ControlStrategy
from crapssim_control.spec_loader import load_spec_file


def _print_engine_hint() -> None:
    print(
        "CrapsSim engine not available.\n"
        "Install it first (one-time):\n"
        '  pip install "git+https://github.com/skent259/crapssim.git"\n'
        "Then re-run:\n"
        "  python run_demo.py [examples/regression.json]\n"
    )


def _mk_rng(seed=None, rng=None):
    if isinstance(rng, np.random.Generator):
        return rng
    if seed is not None:
        return np.random.default_rng(seed)
    # deterministic default for demo stability
    return np.random.default_rng(12345)


def _gen_pairs(n_rolls: int, rng: np.random.Generator) -> List[Tuple[int, int]]:
    # List of (d1,d2), each die in 1..6
    d1 = rng.integers(1, 7, size=n_rolls, endpoint=False)
    d2 = rng.integers(1, 7, size=n_rolls, endpoint=False)
    return list(zip(d1.tolist(), d2.tolist()))


def _gen_totals(n_rolls: int, rng: np.random.Generator) -> List[int]:
    # Totals 2..12 from two fair dice
    d1 = rng.integers(1, 7, size=n_rolls, endpoint=False)
    d2 = rng.integers(1, 7, size=n_rolls, endpoint=False)
    return (d1 + d2).tolist()


def fixed_run_compat(table, n_rolls, **kwargs):
    """
    Cross-version adapter for CrapsSim Table.fixed_run.
    Supports engines that expect seed=, rng=, and/or a required dice_outcomes=.
    - If signature has rng and caller gave seed, convert to rng.
    - If signature requires dice_outcomes, auto-generate from rng/seed.
    - Attempt (d1,d2) pairs first; if that TypeErrors, fallback to totals.
    """
    cls = type(table)
    sig = inspect.signature(cls.fixed_run)
    params = sig.parameters
    names = set(params.keys())

    # Normalize RNG
    seed = kwargs.get("seed", None)
    rng = kwargs.get("rng", None)
    need_rng = ("rng" in names) or ("dice_outcomes" in names)
    if need_rng:
        rng = _mk_rng(seed=seed, rng=rng)
        kwargs.pop("seed", None)
        if "rng" in names:
            kwargs["rng"] = rng
        else:
            # Engine doesn't accept rng; keep it local for dice generation only
            kwargs.pop("rng", None)

    # If dice_outcomes is required (no default), generate deterministically
    dice_param = params.get("dice_outcomes")
    requires_dice = False
    if dice_param is not None and dice_param.default is inspect._empty:
        requires_dice = True

    call_kwargs = {name: kwargs[name] for name in kwargs.keys() if name in names}

    def _call_with_kwargs(extra_kwargs: dict):
        if "n_rolls" in names:
            return table.fixed_run(n_rolls, **extra_kwargs)
        return table.fixed_run(**extra_kwargs)

    if requires_dice:
        # Try (d1,d2) pairs first
        try:
            kwargs_try = dict(call_kwargs)
            kwargs_try["dice_outcomes"] = _gen_pairs(n_rolls, rng or _mk_rng())
            return _call_with_kwargs(kwargs_try)
        except (TypeError, AssertionError):
            # Fallback: totals 2..12
            kwargs_try = dict(call_kwargs)
            kwargs_try["dice_outcomes"] = _gen_totals(n_rolls, rng or _mk_rng())
            return _call_with_kwargs(kwargs_try)

    # No required dice_outcomes: just call through
    return _call_with_kwargs(call_kwargs)


class _DemoStrategyProxy:
    """Lightweight adapter so vanilla Table players can call ControlStrategy."""

    def __init__(self, ctrl):
        self.ctrl = ctrl
        self._prev_point_on: bool | None = None

    def update_bets(self, player):
        table = getattr(player, "table", None)
        if table is None:
            return
        try:
            self.ctrl.update_bets(table)
        except TypeError:
            # Legacy signature without table argument
            self.ctrl.update_bets(table)

    def after_roll(self, player):
        table = getattr(player, "table", None)
        if table is None:
            return
        point_on = bool(getattr(table.point, "status", "Off") == "On")
        total = int(getattr(table.dice, "total", 0))
        event = {"event": "roll"}
        if (self._prev_point_on is True) and total == 7:
            event = {"event": "seven_out"}
        self._prev_point_on = point_on
        try:
            self.ctrl.after_roll(table, event)
        except TypeError:
            try:
                self.ctrl.after_roll(event)
            except TypeError:
                pass


def main(spec_path: str | None = None):
    if Table is None:
        _print_engine_hint()
        raise SystemExit(1) from _ENGINE_IMPORT_ERROR

    spec_file = Path(spec_path or "examples/regression.json")
    if not spec_file.exists():
        print(f"SPEC not found: {spec_file}")
        sys.exit(2)

    spec, spec_deprecations = load_spec_file(spec_file)

    # Table & strategy
    table = Table()
    strat = ControlStrategy(spec, spec_deprecations=spec_deprecations)
    table.add_player(bankroll=300, strategy=_DemoStrategyProxy(strat), name="SpecBot")

    # Run a short session
    fixed_run_compat(table, n_rolls=60, runout=False, verbose=False)

    # Report
    p = table.players[0]
    print(f"Final bankroll: ${getattr(p,'bankroll',0)}")
    # Show current bets snapshot (duck-typed)
    bets = getattr(p, "bets", [])
    if bets:
        print("Active bets:")
        for b in bets:
            kind = getattr(b, "kind", b.__class__.__name__)
            num = getattr(b, "number", None)
            amt = getattr(b, "amount", None)
            print(f" - {kind} {num or ''} = ${amt}")
    else:
        print("No active bets at end.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
