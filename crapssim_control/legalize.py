# crapssim_control/legalize.py
"""
Legalization helpers for bet amounts.

- Flat/Place bet legalization (existing): step sizes by number & bubble flag
- Odds legalization (new): cap by policy (3-4-5x, 2x, 5x, 10x, or int multiplier)
  and round to "clean payout" steps per point (unless bubble, which is $1 steps).
"""

from typing import Optional

# ---- Flat/place increments ----

def _place_step_for(number: Optional[int], bubble: bool) -> int:
    if bubble:
        return 1
    if number in (6, 8):
        return 6
    if number in (5, 9):
        return 5
    if number in (4, 10):
        return 5
    # flat bets & others default to table min step when not bubble
    return None  # sentinel meaning "use table min step"

def _round_up(value: int, step: int) -> int:
    if step <= 1:
        return int(value)
    rem = value % step
    return value if rem == 0 else value + (step - rem)

def legalize_amount(number: Optional[int], raw_amount: int, bubble: bool, table_level: int) -> int:
    """
    Legalize a base/flat/place amount:
      - floor at table minimum
      - bubble: $1 steps
      - non-bubble place: 6/8 in $6s, 5/9 in $5s, 4/10 in $5s
      - non-bubble flat: step at table min
    """
    amt = max(int(raw_amount), int(table_level))
    if bubble:
        return _round_up(amt, 1)

    step = _place_step_for(number, bubble=False)
    if step is None:
        step = int(table_level)
    return _round_up(amt, step)

# ---- Odds legalization ----

def _max_multiple_for_point(point: int, policy: str | int) -> int:
    """
    Determine the maximum odds multiple relative to the flat bet for a given point.
    - policy: "3-4-5x" (default), "2x", "5x", "10x", or an integer multiplier (e.g., 20)
    """
    if isinstance(policy, int):
        return int(policy)
    p = str(policy).lower().strip()

    if p in ("2x", "2"):
        return 2
    if p in ("5x", "5"):
        return 5
    if p in ("10x", "10"):
        return 10
    # default: 3-4-5x
    if point in (4, 10):
        return 3
    if point in (5, 9):
        return 4
    if point in (6, 8):
        return 5
    # if somehow no point, be conservative
    return 0

def _odds_step_for_point(point: int, bubble: bool) -> int:
    """
    Step size for PASS odds that yields clean payouts (avoids breakage).
    - On bubble, allow $1 steps (engine may handle cents or round; we keep $1 granularity).
    - On live tables, choose steps that avoid nickels in payouts:
        4/10 pay 2:1  -> $1 step OK
        5/9  pay 3:2  -> $2 step
        6/8  pay 6:5  -> $5 step
    """
    if bubble:
        return 1
    if point in (4, 10):
        return 1
    if point in (5, 9):
        return 2
    if point in (6, 8):
        return 5
    return 1

def legalize_odds(
    point: Optional[int],
    desired_odds: int,
    base_flat: int,
    *,
    bubble: bool,
    policy: str | int = "3-4-5x",
) -> int:
    """
    Legalize PASS ODDS amount:
      1) Cap at (max_multiple_for_point(policy) * base_flat)
      2) Round UP to the clean payout step for the point (unless bubble: $1)
      3) Clamp to >= 0

    Notes:
      - If 'point' is None/invalid, returns 0 (no odds on comeout).
      - This function targets PASS odds. LAY (Don't Pass) odds may need separate rules;
        for now, callers can reuse this or pass through as-is.
    """
    if point not in (4, 5, 6, 8, 9, 10):
        return 0

    cap_mult = _max_multiple_for_point(point, policy)
    if cap_mult <= 0:
        return 0

    cap = int(cap_mult * max(0, int(base_flat)))
    amt = max(0, int(desired_odds))
    amt = min(amt, cap)

    step = _odds_step_for_point(point, bubble=bubble)
    # Round DOWN to avoid accidentally exceeding cap after rounding
    if step > 1 and amt % step != 0:
        amt = amt - (amt % step) + (0 if amt % step == 0 else 0)  # ensure floor to step
        amt = amt - (amt % step)
    return max(0, amt)