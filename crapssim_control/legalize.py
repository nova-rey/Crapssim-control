def place_step(number: int, bubble: bool) -> int:
    """Return the legal increment for a Place bet on this number."""
    if bubble:
        return 1
    if number in (6, 8):
        return 6
    return 5  # for 4, 5, 9, 10

def legalize_amount(number: int | None, amount: int, bubble: bool, table_level: int) -> int:
    """
    Round a raw amount up to the nearest legal increment.
    - number: bet number (None for flat bets like Pass/Field)
    - amount: raw expression result
    - bubble: True for bubble craps (increments $1)
    - table_level: table minimum (e.g. 5/10/15/25)
    """
    amt = int(max(amount, table_level))
    if number is None:
        # flat bets (pass, dp, field)
        step = 1 if bubble else table_level
        return ((amt + step - 1) // step) * step
    step = place_step(number, bubble)
    return ((amt + step - 1) // step) * step