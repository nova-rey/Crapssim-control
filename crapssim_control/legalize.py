"""
legalize.py -- Batch 14 (Runtime Legalizer)

Helpers to turn raw bet amounts into table-legal amounts.

Config (table_cfg dict; all optional):
  - bubble: bool (default False)          # bubble craps allows $1 increments generally
  - level: int (default 10)               # table minimum for *line* bets (pass/don't), not field
  - place_410_increment: int (default 5)  # increment for place 4/10 (some houses use 10)
  - max_odds_multiple: float (default 3.0)# cap odds at N x base line bet

Public:
  - legalize_amount(bet_type, raw_amount, table_cfg, point=None, base_line_bet=None)
  - cap_odds_amount(base_line_bet, raw_odds, max_multiple)
"""

from __future__ import annotations

from typing import Dict, Tuple, Optional

_PLACE_INCREMENTS = {
    6: 6,
    8: 6,
    5: 5,
    9: 5,
    4: "cfg_410",
    10: "cfg_410",
}


def _cfg(table_cfg: Optional[Dict]) -> Dict:
    cfg = {
        "bubble": False,
        "level": 10,
        "place_410_increment": 5,
        "max_odds_multiple": 3.0,
    }
    if table_cfg:
        cfg.update(table_cfg)
    return cfg


def _round_down(amount: float, step: int) -> int:
    if step <= 0:
        return int(max(0, amount))
    return int(max(0, amount // step) * step)


def cap_odds_amount(base_line_bet: float, raw_odds: float, max_multiple: float) -> int:
    """
    Cap odds at base_line_bet * max_multiple. Round DOWN to $1 increment.
    """
    cap = float(base_line_bet) * float(max_multiple)
    legal = min(max(0.0, float(raw_odds)), cap)
    return int(legal // 1)  # $1 granularity by default


def legalize_amount(
    bet_type: str,
    raw_amount: float,
    table_cfg: Optional[Dict] = None,
    *,
    point: Optional[int] = None,
    base_line_bet: Optional[float] = None,
) -> Tuple[int, Dict]:
    """
    Returns (legal_amount, flags)

    - bet_type: canonical bet name (e.g., pass_line, dont_pass, place_6, lay_10, odds_6_pass)
    - raw_amount: desired amount before legalization
    - table_cfg: dict per _cfg()
    - point: current point (needed for certain validations)
    - base_line_bet: the corresponding line bet amount for odds clamping

    Flags:
      - {"clamped": bool, "reason": str|None}
    """
    cfg = _cfg(table_cfg or {})
    flags = {"clamped": False, "reason": None}

    bt = str(bet_type)

    # Negative or zero requests are treated as zero (caller may interpret as 'clear')
    try:
        amt = float(raw_amount)
    except Exception:
        amt = 0.0
    if amt <= 0:
        return 0, flags

    # Bubble or not affects increments for place bets primarily
    bubble = bool(cfg.get("bubble", False))

    # Line bets: apply table minimum only to pass/don't; others are $1 increments
    if bt in {"pass_line", "dont_pass"}:
        min_level = int(cfg.get("level", 10))
        legal = int(amt // 1)
        if legal < min_level:
            flags["clamped"] = True
            flags["reason"] = f"min_level_{min_level}"
            legal = min_level
        return legal, flags

    # Come / Don't Come: $1 increments, no level clamp here
    if bt in {"come", "dont_come"}:
        legal = int(amt // 1)
        if legal < amt:
            flags["clamped"] = True
            flags["reason"] = "come_step_1"
        return legal, flags

    # Field: $1 increments, explicitly no level clamp
    if bt == "field":
        legal = int(amt // 1)
        if legal < amt:
            flags["clamped"] = True
            flags["reason"] = "field_step_1"
        return legal, flags

    # Place bets
    if bt.startswith("place_"):
        try:
            num = int(bt.split("_", 1)[1])
        except Exception:
            return 0, flags
        if bubble:
            step = 1
        else:
            step_cfg = _PLACE_INCREMENTS.get(num)
            if step_cfg == "cfg_410":
                step = int(cfg.get("place_410_increment", 5))
            else:
                step = int(step_cfg or 1)
        legal = _round_down(amt, step)
        if legal < amt:
            flags["clamped"] = True
            flags["reason"] = f"place_step_{step}"
        return legal, flags

    # Lays (simplify: $1 granularity; more complex vig rules can be layered later)
    if bt.startswith("lay_"):
        legal = int(amt // 1)
        if legal < amt:
            flags["clamped"] = True
            flags["reason"] = "lay_step_1"
        return legal, flags

    # Odds: odds_{point}_pass or odds_{point}_dont
    if bt.startswith("odds_"):
        parts = bt.split("_")
        if len(parts) >= 3:
            try:
                odds_point = int(parts[1])  # noqa: F841 (reserved for future validation)
            except Exception:
                odds_point = None  # noqa: F841
        max_mult = float(cfg.get("max_odds_multiple", 3.0))
        base = float(base_line_bet or 0.0)
        capped = cap_odds_amount(base, amt, max_mult)
        if capped < amt:
            flags["clamped"] = True
            flags["reason"] = f"odds_cap_{max_mult}x"
        return capped, flags

    # Fallback: $1 granularity
    legal = int(amt // 1)
    if legal < amt:
        flags["clamped"] = True
        flags["reason"] = "fallback_step_1"
    return legal, flags