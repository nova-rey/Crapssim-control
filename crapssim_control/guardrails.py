from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Tuple, Iterable


# =============================================================================
# Models and presets (for future enforcement; today we only emit notes)
# =============================================================================

@dataclass(frozen=True)
class OddsPolicy:
    """Max odds as a multiple of the flat line bet (generic cap)."""
    type: str                 # "flat-multiple" or "three-four-five" (future)
    max_multiple: float = 0.0


@dataclass(frozen=True)
class Increments:
    """Minimum increments per betting area."""
    pass_line: int
    field: int
    place_4_10: int
    place_5_9: int
    place_6_8: int


@dataclass(frozen=True)
class TableLimits:
    """Overall and per-area maximums."""
    min_bet: int
    max_bet: int
    max_place: int | None = None
    max_field: int | None = None
    max_odds_multiple: float | None = None


@dataclass(frozen=True)
class GuardrailConfig:
    """Bundle of policies that define a table's constraints."""
    name: str
    odds: OddsPolicy
    increments: Increments
    limits: TableLimits


LIVE_DEFAULTS = GuardrailConfig(
    name="live-defaults",
    odds=OddsPolicy(type="flat-multiple", max_multiple=5.0),
    increments=Increments(
        pass_line=5, field=5,
        place_4_10=5, place_5_9=5, place_6_8=6,
    ),
    limits=TableLimits(min_bet=5, max_bet=1000, max_place=1500, max_field=1000, max_odds_multiple=5.0),
)

BUBBLE_DEFAULTS = GuardrailConfig(
    name="bubble-defaults",
    odds=OddsPolicy(type="flat-multiple", max_multiple=5.0),
    increments=Increments(
        pass_line=1, field=1,
        place_4_10=1, place_5_9=1, place_6_8=1,
    ),
    limits=TableLimits(min_bet=1, max_bet=300, max_place=300, max_field=300, max_odds_multiple=5.0),
)

HOT_DEFAULTS = GuardrailConfig(
    name="hot-defaults",
    odds=OddsPolicy(type="flat-multiple", max_multiple=10.0),
    increments=Increments(
        pass_line=5, field=5,
        place_4_10=5, place_5_9=5, place_6_8=6,
    ),
    limits=TableLimits(min_bet=5, max_bet=5000, max_place=5000, max_field=2000, max_odds_multiple=10.0),
)


def _select_defaults(*, bubble: bool, hot_table: bool) -> GuardrailConfig:
    if hot_table:
        return HOT_DEFAULTS
    return BUBBLE_DEFAULTS if bubble else LIVE_DEFAULTS


# =============================================================================
# Public API (dual-mode) -- compatible with both tests and CLI
# =============================================================================

def apply_guardrails(
    spec: Dict[str, Any],
    *args,
    **kwargs
):
    """
    Dual-mode helper.

    1) **Intent-processor mode** (what tests expect):
         apply_guardrails(spec, vs, intents) -> intents
       - Three-argument call where the second arg is a "vs"/context object and
         the third is a list of bet intents (dicts). This must be a NO-OP
         today and simply return the intents unchanged.

    2) **CLI descriptor mode** (what our CLI uses when --guardrails is present):
         apply_guardrails(spec, hot_table=True/False, guardrails=True/False)
           -> (spec, notes)
       - Keyword-only flags; returns the *unmodified* spec and a list of human-
         readable notes describing which preset would be used. This also must
         not mutate the spec today.

    We detect the mode by argument pattern.
    """
    # ---- Mode 1: (spec, vs, intents) -> intents (NO-OP) ----
    if len(args) >= 2 and isinstance(args[-1], list):
        intents = args[-1]
        # Guarantee we return the same shape; do not mutate.
        return intents

    # ---- Mode 2: (spec, *, hot_table=..., guardrails=...) -> (spec, notes) ----
    hot_table = bool(kwargs.get("hot_table", False))
    guardrails_enabled = bool(kwargs.get("guardrails", False))
    notes: List[str] = []
    if not guardrails_enabled:
        # Truly no-op: return unmodified spec and no notes
        return spec, notes

    table = spec.get("table", {}) if isinstance(spec, dict) else {}
    bubble = bool(table.get("bubble", False))
    cfg = _select_defaults(bubble=bubble, hot_table=hot_table)

    notes.append(f"guardrails: using preset '{cfg.name}' (bubble={bubble}, hot_table={hot_table})")
    notes.append(f"guardrails: odds policy -> type={cfg.odds.type}, max_multiple={_fmt_mult(cfg.odds.max_multiple)}")
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
    return spec, notes


def scale_bets_if_hot(
    spec: Dict[str, Any],
    vs: object,
    intents: List[Dict[str, Any]],
    *args,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Placeholder for a future scaling processor used when --hot-table is passed.

    Current behavior (by design for CI): **NO-OP** -- return intents unchanged.
    """
    return intents


# =============================================================================
# Helpers
# =============================================================================

def _fmt_mult(x: float) -> str:
    # Show 10x not 10.0x
    if float(x).is_integer():
        return f"{int(x)}x"
    return f"{x}x"