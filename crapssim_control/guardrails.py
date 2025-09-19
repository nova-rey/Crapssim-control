from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class OddsPolicy:
    """
    Craps odds policy.

    Common presets:
      - "3-4-5x": standard Vegas: 4/10:3x, 5/9:4x, 6/8:5x (on top of line bet)
      - "multiple": flat multiplier for all points (e.g., 10x, 100x, 1000x)
      - "unlimited": treat as effectively uncapped (still subject to table max)
    """
    kind: str = "3-4-5x"        # "3-4-5x" | "multiple" | "unlimited"
    multiple: float = 1.0       # used when kind == "multiple"

    def max_odds_multiple_for_point(self, point: int) -> Optional[float]:
        """
        Returns the odds multiple allowed for a given point number (4,5,6,8,9,10),
        or None if effectively unlimited.
        """
        if self.kind == "unlimited":
            return None
        if self.kind == "multiple":
            return max(0.0, float(self.multiple))
        # default: 3-4-5x
        if point in (4, 10):
            return 3.0
        if point in (5, 9):
            return 4.0
        if point in (6, 8):
            return 5.0
        return 0.0


@dataclass(frozen=True)
class Increments:
    """
    Minimum bet increments per bet family. These are *table norms*, not payouts.
    """
    line: float = 1.0               # Pass/Don't min step
    field: float = 1.0
    place_4_10: float = 5.0
    place_5_9: float = 5.0
    place_6_8: float = 6.0
    buy_4_10: float = 5.0
    buy_5_9: float = 5.0
    buy_6_8: float = 6.0


@dataclass(frozen=True)
class TableRules:
    """
    All guardrails used to shape/limit wagers before they hit the engine.
    """
    # hard caps
    table_max: float = 5000.0            # absolute max any single bet may reach
    allow_lay: bool = True               # allow lay bets at this table

    # odds behavior
    odds: OddsPolicy = OddsPolicy()

    # increment behavior (bubble tables often accept $1 steps everywhere)
    increments: Increments = Increments()

    # misc
    bubble: bool = False                 # when True, relax increments to $1
    level: int = 10                      # table minimum unit

    def normalized(self) -> "TableRules":
        """
        Apply bubble-driven normalization (e.g., $1 steps everywhere).
        """
        if not self.bubble:
            return self
        # on bubble, we typically allow $1 steps across the board
        inc = Increments(
            line=1.0,
            field=1.0,
            place_4_10=1.0,
            place_5_9=1.0,
            place_6_8=1.0,
            buy_4_10=1.0,
            buy_5_9=1.0,
            buy_6_8=1.0,
        )
        return TableRules(
            table_max=self.table_max,
            allow_lay=self.allow_lay,
            odds=self.odds,
            increments=inc,
            bubble=self.bubble,
            level=self.level,
        )


def _read_float(d: Dict[str, Any], key: str, default: float) -> float:
    try:
        return float(d.get(key, default))
    except Exception:
        return default


def derive_table_rules(spec: Dict[str, Any],
                       *,
                       hot_table: bool = False,
                       overrides: Optional[Dict[str, Any]] = None) -> TableRules:
    """
    Build TableRules from the spec (+ optional CLI overrides).
    This does *not* mutate behavior by itself; enforcement will be wired
    where bets are created.

    Recognized spec keys:
      spec.table.level
      spec.table.bubble
      spec.table.table_max
      spec.table.allow_lay
      spec.table.odds.kind ("3-4-5x" | "multiple" | "unlimited")
      spec.table.odds.multiple (float, used when kind == "multiple")
      spec.table.increments.{...} (see Increments fields)
    """
    table = dict(spec.get("table", {}))
    if overrides:
        # shallow override of top-level table keys if provided by CLI
        table.update(overrides)

    bubble = bool(table.get("bubble", False))
    level = int(table.get("level", 10))

    # odds
    odds_cfg = dict(table.get("odds", {})) if isinstance(table.get("odds"), dict) else {}
    kind = str(odds_cfg.get("kind", "3-4-5x"))
    multiple = _read_float(odds_cfg, "multiple", 1.0)
    odds = OddsPolicy(kind=kind, multiple=multiple)

    # increments
    inc_cfg = dict(table.get("increments", {})) if isinstance(table.get("increments"), dict) else {}
    increments = Increments(
        line=_read_float(inc_cfg, "line", 1.0),
        field=_read_float(inc_cfg, "field", 1.0),
        place_4_10=_read_float(inc_cfg, "place_4_10", 5.0),
        place_5_9=_read_float(inc_cfg, "place_5_9", 5.0),
        place_6_8=_read_float(inc_cfg, "place_6_8", 6.0),
        buy_4_10=_read_float(inc_cfg, "buy_4_10", 5.0),
        buy_5_9=_read_float(inc_cfg, "buy_5_9", 5.0),
        buy_6_8=_read_float(inc_cfg, "buy_6_8", 6.0),
    )

    # hard caps
    table_max = _read_float(table, "table_max", 5000.0)
    allow_lay = bool(table.get("allow_lay", True))

    rules = TableRules(
        table_max=table_max,
        allow_lay=allow_lay,
        odds=odds,
        increments=increments,
        bubble=bubble,
        level=level,
    )

    # "hot table" convenience: if requested, we can optionally relax table_max
    # or bump odds. For now, we just keep it as a semantic flag; enforcement will
    # read it later if needed. No implicit behavior change here.
    return rules.normalized()


def describe_table_rules(rules: TableRules) -> str:
    """Human-readable one-pager for logging/help."""
    inc = rules.increments
    odds = rules.odds
    odds_str = (
        "unlimited"
        if odds.kind == "unlimited"
        else (f"{odds.multiple:.0f}x (all points)" if odds.kind == "multiple" else "3-4-5x")
    )
    lines = [
        f"Guardrails: table_max=${rules.table_max:,.0f}, bubble={rules.bubble}, level=${rules.level}",
        f"  Odds policy: {odds_str}",
        "  Increments:",
        f"    line=${inc.line:.0f} field=${inc.field:.0f}",
        f"    place 4/10=${inc.place_4_10:.0f} 5/9=${inc.place_5_9:.0f} 6/8=${inc.place_6_8:.0f}",
        f"    buy   4/10=${inc.buy_4_10:.0f} 5/9=${inc.buy_5_9:.0f} 6/8=${inc.buy_6_8:.0f}",
    ]
    return "\n".join(lines)