# crapssim_control/legalize_legacy.py
"""
Legalization helpers for bet amounts.

- Flat/Place bet legalization:
    • floor to table min
    • bubble: $1 steps
    • non-bubble place: 6/8 in $6s; 5/9/4/10 in $5s; flats step at table min

- PASS odds legalization (legalize_odds):
    • Cap by policy (3-4-5x default, or "2x"/"5x"/"10x"/int)
    • Round to clean-payout steps for the point (bubble: $1 steps)

- DON'T PASS lay odds legalization (legalize_lay_odds):
    • Cap by policy on **potential win** equal to multiple * flat
      (e.g., 3-4-5x → you may lay enough to win 3x/4x/5x the flat)
    • Convert win-cap to a **lay amount** via point’s payout ratio
      4/10: win = lay * 1/2 → lay_max = win_cap * 2 (step 2)
      5/9 : win = lay * 2/3 → lay_max = win_cap * 3/2 (step 3)
      6/8 : win = lay * 5/6 → lay_max = win_cap * 6/5 (step 6)
    • Round **down** to step; bubble: $1 steps
"""

from typing import Optional

# ---- Flat/place increments ----

def _place_step_for(number: Optional[int], bubble: bool) -> int:
    if bubble:
        return 1
    if number in (6, 8):
        return 6
    if number in (5, 9, 4, 10):
        return 5
    # Flats use table-min step when not bubble
    return 0  # sentinel meaning "use table-min step"

def _round_up(value: int, step: int) -> int:
    if step <= 1:
        return int(value)
    rem = value % step
    return value if rem == 0 else value + (step - rem)

def _round_down(value: int, step: int) -> int:
    if step <= 1:
        return int(value)
    return value - (value % step)

def legalize_amount(number: Optional[int], raw_amount: int, bubble: bool, table_level: int) -> int:
    """
    Legalize a base/flat/place amount:
      - floor at table minimum
      - bubble: $1 steps
      - non-bubble place: 6/8 in $6s; 5/9/4/10 in $5s
      - non-bubble flat: step at table min
    """
    amt = max(int(raw_amount), int(table_level))
    if bubble:
        return _round_up(amt, 1)

    step = _place_step_for(number, bubble=False)
    if step == 0:
        step = int(table_level)
    return _round_up(amt, step)

# ---- Odds legalization (PASS) ----

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
    return 0

def _pass_odds_step(point: int, bubble: bool) -> int:
    # steps chosen to avoid cents in payouts for live tables
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
      2) Round DOWN to the clean payout step for the point (unless bubble: $1)
      3) Clamp to >= 0
    """
    if point not in (4, 5, 6, 8, 9, 10):
        return 0

    cap_mult = _max_multiple_for_point(point, policy)
    if cap_mult <= 0:
        return 0

    cap = int(cap_mult * max(0, int(base_flat)))
    amt = min(max(0, int(desired_odds)), cap)

    step = _pass_odds_step(point, bubble=bubble)
    amt = _round_down(amt, step)
    return max(0, amt)

# ---- Lay odds legalization (DON'T PASS) ----

def _lay_odds_step(point: int, bubble: bool) -> int:
    """
    Steps chosen so the payout (which is fractional) avoids cents:
      4/10 lay pays 1:2  -> $2 steps
      5/9  lay pays 2:3  -> $3 steps
      6/8  lay pays 5:6  -> $6 steps
    Bubble allows $1 steps.
    """
    if bubble:
        return 1
    if point in (4, 10):
        return 2
    if point in (5, 9):
        return 3
    if point in (6, 8):
        return 6
    return 1

def _lay_amount_cap_from_win_cap(point: int, win_cap: int) -> int:
    """
    Convert a cap on potential WIN into a max lay amount for the point:
      win = lay * r  => lay_max = floor(win_cap / r_inverse)
    Ratios:
      4/10: win = lay * (1/2)  => lay_max = win_cap * 2
      5/9 : win = lay * (2/3)  => lay_max = floor(win_cap * 3/2)
      6/8 : win = lay * (5/6)  => lay_max = floor(win_cap * 6/5)
    """
    if point in (4, 10):
        return int(win_cap * 2)
    if point in (5, 9):
        return int((win_cap * 3) // 2)
    if point in (6, 8):
        return int((win_cap * 6) // 5)
    return 0

def legalize_lay_odds(
    point: Optional[int],
    desired_lay: int,
    base_flat: int,
    *,
    bubble: bool,
    policy: str | int = "3-4-5x",
) -> int:
    """
    Legalize DON'T PASS LAY ODDS amount:
      1) Compute win-cap = (max_multiple_for_point(policy) * base_flat)
      2) Convert win-cap → lay_max by point ratio (see _lay_amount_cap_from_win_cap)
      3) Enforce cap (min(desired, lay_max))
      4) Round DOWN to lay step (2 / 3 / 6 non-bubble; $1 bubble)
    """
    if point not in (4, 5, 6, 8, 9, 10):
        return 0

    cap_mult = _max_multiple_for_point(point, policy)
    if cap_mult <= 0:
        return 0

    win_cap = int(cap_mult * max(0, int(base_flat)))
    lay_cap = _lay_amount_cap_from_win_cap(point, win_cap)
    amt = min(max(0, int(desired_lay)), lay_cap)

    step = _lay_odds_step(point, bubble=bubble)
    amt = _round_down(amt, step)
    return max(0, amt)