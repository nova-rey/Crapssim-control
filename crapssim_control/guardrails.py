from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Tuple


# ---- Data models we will use when we wire real enforcement (Batch 2) ----

@dataclass(frozen=True)
class OddsPolicy:
    """Maximum odds as a multiple of the flat Pass/Don’t (e.g. 3-4-5x ≈ 5x cap by point)."""
    type: str  # "flat-multiple" for simple cap, "three-four-five" for 3-4-5x
    max_multiple: float = 0.0  # used when type == "flat-multiple"
    # For 3-4-5x, the effective max multiple differs by point; we’ll compute that in enforcement.


@dataclass(frozen=True)
class Increments:
    """Smallest allowed bet increments per area (e.g. $6 on 6/8 in live; $1 on bubble)."""
    pass_line: int
    field: int
    place_4_10: int
    place_5_9: int
    place_6_8: int


@dataclass(frozen=True)
class TableLimits:
    """Overall min/max and per-area maximums (optional)."""
    min_bet: int
    max_bet: int
    max_place: int | None = None
    max_field: int | None = None
    max_odds_multiple: float | None = None  # convenience mirror from OddsPolicy


@dataclass(frozen=True)
class GuardrailConfig:
    """Bundle of rules that define a table’s policy."""
    name: str
    odds: OddsPolicy
    increments: Increments
    limits: TableLimits


# ---- Default presets (kept simple and conservative) ----

# Typical live table (non-bubble): enforce correct place increments and a modest table max
LIVE_DEFAULTS = GuardrailConfig(
    name="live-defaults",
    odds=OddsPolicy(type="flat-multiple", max_multiple=5.0),  # ~ 5x generic cap
    increments=Increments(
        pass_line=5,
        field=5,
        place_4_10=5,   # many houses still like $5 steps on 4/10
        place_5_9=5,    # $5 steps
        place_6_8=6,    # $6 steps to keep payouts clean
    ),
    limits=TableLimits(min_bet=5, max_bet=1000, max_place=1500, max_field=1000, max_odds_multiple=5.0),
)

# Bubble tables are more permissive on increments, but often lower table max
BUBBLE_DEFAULTS = GuardrailConfig(
    name="bubble-defaults",
    odds=OddsPolicy(type="flat-multiple", max_multiple=5.0),
    increments=Increments(
        pass_line=1,
        field=1,
        place_4_10=1,
        place_5_9=1,
        place_6_8=1,
    ),
    limits=TableLimits(min_bet=1, max_bet=300, max_place=300, max_field=300, max_odds_multiple=5.0),
)

# A "hot house" preset we’ll use when the --hot-table flag is passed (looser caps)
HOT_DEFAULTS = GuardrailConfig(
    name="hot-defaults",
    odds=OddsPolicy(type="flat-multiple", max_multiple=10.0),
    increments=Increments(
        pass_line=5,
        field=5,
        place_4_10=5,
        place_5_9=5,
        place_6_8=6,
    ),
    limits=TableLimits(min_bet=5, max_bet=5000, max_place=5000, max_field=2000, max_odds_multiple=10.0),
)


def select_defaults(*, bubble: bool, hot_table: bool) -> GuardrailConfig:
    """
    Pick a preset based on table type and 'hot table' toggle.
    This is used only for producing human-readable notes today.
    """
    if hot_table:
        return HOT_DEFAULTS
    return BUBBLE_DEFAULTS if bubble else LIVE_DEFAULTS


# ---- Public API expected by tests/CLI ----

def apply_guardrails(spec: Dict[str, Any], hot_table: bool = False, guardrails: bool = False) -> Tuple[Dict[str, Any], List[str]]:
    """
    Batch 2 (phase 1): **No-op on the spec**, return informational notes only.

    Why a no-op?
    - We haven’t wired enforcement into bet placement yet (that’s the next sub-batch).
    - CI/tests expect that turning flags on does not mutate the user spec.
    - This function must exist (tests import it) and be stable.

    Returns:
      (spec, notes)
      - spec: the ORIGINAL dict (unmodified)
      - notes: a list of strings describing what would be enforced once wired
    """
    notes: List[str] = []

    # If the flag isn’t enabled, explicitly say we did nothing.
    if not guardrails:
        return spec, notes  # truly no-op

    table = spec.get("table", {}) if isinstance(spec, dict) else {}
    bubble = bool(table.get("bubble", False))
    cfg = select_defaults(bubble=bubble, hot_table=hot_table)

    # Compose human-readable notes (CLI will log these at INFO when --guardrails is present)
    notes.append(f"guardrails: using preset '{cfg.name}' (bubble={bubble}, hot_table={hot_table})")
    notes.append(
        f"guardrails: odds policy -> type={cfg.odds.type}, max_multiple={cfg.odds.max_multiple:g}x"
    )
    notes.append(
        "guardrails: increments -> "
        f"PL={cfg.increments.pass_line}, Field={cfg.increments.field}, "
        f"P4/10={cfg.increments.place_4_10}, P5/9={cfg.increments.place_5_9}, P6/8={cfg.increments.place_6_8}"
    )
    notes.append(
        "guardrails: limits -> "
        f"min={cfg.limits.min_bet}, max={cfg.limits.max_bet}, "
        f"max_place={cfg.limits.max_place}, max_field={cfg.limits.max_field}, "
        f"max_odds≈{cfg.limits.max_odds_multiple}"
    )

    # IMPORTANT: do not mutate the spec yet.
    return spec, notes