from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional


# ---------------------------
# Built-in preset profiles
# ---------------------------

DEFAULT_PROFILES: Dict[str, Dict[str, Any]] = {
    # Typical live casino: 3-4-5x odds, $5 increments on 4/5/9/10, $6 on 6/8.
    "live_3_4_5x": {
        "enforcement": "warning",  # "warning" | "strict"
        "max": {
            "pass": 1000,
            "odds": {"type": "3_4_5x"},
            "place": 1000,
            "field": 1000,
        },
        "increments": {
            "place": {"4": 5, "5": 5, "6": 6, "8": 6, "9": 5, "10": 5},
            "field": 5,
            "pass": 5,
        },
        "allow": {"buy": True, "lay": True, "hardways": True},
    },
    # Bubble / stadium style: fine-grained increments, huge odds multiplier.
    "bubble_1000x": {
        "enforcement": "warning",
        "max": {
            "pass": 5000,
            "odds": {"type": "flat", "multiplier": 1000},
            "place": 5000,
            "field": 5000,
        },
        "increments": {
            "place": {"4": 1, "5": 1, "6": 1, "8": 1, "9": 1, "10": 1},
            "field": 1,
            "pass": 1,
        },
        "allow": {"buy": True, "lay": True, "hardways": True},
    },
}


@dataclass
class TableRulesResult:
    errors: List[str]
    warnings: List[str]
    rules: Dict[str, Any]


# ---------------------------
# Public helpers
# ---------------------------


def get_table_rules(spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge user-specified `table_rules` with a named profile if provided.
    If no table_rules are present, returns {} (meaning: no extra enforcement).
    """
    tr = dict(spec.get("table_rules") or {})
    if not tr:
        return {}

    profile_name = tr.get("profile")
    base = {}
    if isinstance(profile_name, str) and profile_name in DEFAULT_PROFILES:
        # Merge: user values override profile defaults
        base = _deepcopy(DEFAULT_PROFILES[profile_name])

    # Shallow merge at top level, then merge nested dicts we know about
    out: Dict[str, Any] = {**base, **tr}
    for key in ("max", "increments", "allow"):
        out[key] = {**base.get(key, {}), **tr.get(key, {})}
        # If it's the "place" sub-map under increments, merge that too
        if key == "increments":
            place_base = base.get("increments", {}).get("place", {}) or {}
            place_tr = tr.get("increments", {}).get("place", {}) or {}
            out["increments"]["place"] = {**place_base, **place_tr}

    if "enforcement" not in out:
        # default to "warning" so we don't break existing flows
        out["enforcement"] = "warning"

    return out


def validate_table_rules(spec: Dict[str, Any]) -> TableRulesResult:
    """
    Validate the (optional) `table_rules` block. If the block is missing,
    returns no errors/warnings and empty rules.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if "table_rules" not in spec or not spec.get("table_rules"):
        return TableRulesResult(errors, warnings, {})

    rules = get_table_rules(spec)

    # enforcement
    enf = rules.get("enforcement", "warning")
    if enf not in ("warning", "strict"):
        errors.append("table_rules.enforcement must be 'warning' or 'strict'")

    # profile (optional, but if provided it should exist)
    prof = rules.get("profile")
    if prof is not None and not isinstance(prof, str):
        errors.append("table_rules.profile must be a string")
    if isinstance(prof, str) and prof not in DEFAULT_PROFILES:
        warnings.append(f"Unknown table_rules.profile '{prof}' (using only explicit values)")

    # max
    max_blk = rules.get("max", {})
    if not isinstance(max_blk, dict):
        errors.append("table_rules.max must be an object")
    else:
        for k in ("pass", "place", "field"):
            v = max_blk.get(k)
            if v is not None and not _is_positive_number(v):
                errors.append(f"table_rules.max.{k} must be a positive number")
        # odds
        odds = max_blk.get("odds")
        if odds is not None:
            if not isinstance(odds, dict):
                errors.append("table_rules.max.odds must be an object")
            else:
                typ = odds.get("type")
                if typ not in ("3_4_5x", "flat"):
                    errors.append("table_rules.max.odds.type must be '3_4_5x' or 'flat'")
                if typ == "flat":
                    mult = odds.get("multiplier")
                    if not _is_positive_number(mult):
                        errors.append("table_rules.max.odds.multiplier must be a positive number")

    # increments
    inc_blk = rules.get("increments", {})
    if inc_blk and not isinstance(inc_blk, dict):
        errors.append("table_rules.increments must be an object")
    else:
        # pass / field increments can be a positive number
        for k in ("pass", "field"):
            v = inc_blk.get(k)
            if v is not None and not _is_positive_number(v):
                errors.append(f"table_rules.increments.{k} must be a positive number")

        # place increments: map of point -> positive number
        place_inc = inc_blk.get("place", {})
        if place_inc and not isinstance(place_inc, dict):
            errors.append("table_rules.increments.place must be an object")
        else:
            for pt, inc in (place_inc or {}).items():
                if str(pt) not in {"4", "5", "6", "8", "9", "10"}:
                    warnings.append(f"table_rules.increments.place contains unknown point '{pt}'")
                if not _is_positive_number(inc):
                    errors.append(f"table_rules.increments.place.{pt} must be a positive number")

    # allow
    allow_blk = rules.get("allow", {})
    if allow_blk and not isinstance(allow_blk, dict):
        errors.append("table_rules.allow must be an object")
    else:
        for k, v in (allow_blk or {}).items():
            if not isinstance(v, bool):
                errors.append(f"table_rules.allow.{k} must be a boolean")

    return TableRulesResult(errors, warnings, rules)


# ---------------------------
# (Future) Normalization hooks
# ---------------------------


def normalize_amount(
    bet_type: str,
    amount: float,
    point: Optional[int],
    rules: Dict[str, Any],
) -> Tuple[float, List[str]]:
    """
    Given a raw intended bet amount, return a normalized (legal) amount
    according to increments. Returns (normalized_amount, warnings).

    NOTE: This is a helper for future Batch 2.2 where we auto-normalize.
    Right now, we DO NOT change amounts unless the caller opts in.
    """
    warns: List[str] = []
    if not rules:
        return amount, warns

    inc_blk = rules.get("increments") or {}
    if bet_type.startswith("place_"):
        pt = bet_type.split("_", 1)[1]
        inc_map = inc_blk.get("place") or {}
        inc = inc_map.get(str(pt))
    else:
        inc = inc_blk.get(bet_type)

    if _is_positive_number(inc):
        normalized = max(0, round(amount / inc)) * inc  # snap down to nearest increment
        if normalized != amount:
            warns.append(f"{bet_type}: adjusted {amount} -> {normalized} to match increment {inc}")
        return float(normalized), warns

    return amount, warns


# ---------------------------
# internals
# ---------------------------


def _is_positive_number(x: Any) -> bool:
    try:
        return float(x) > 0
    except Exception:
        return False


def _deepcopy(obj: Any) -> Any:
    # Small, dependency-free deepcopy suitable for our profile dicts.
    if isinstance(obj, dict):
        return {k: _deepcopy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deepcopy(v) for v in obj]
    return obj
