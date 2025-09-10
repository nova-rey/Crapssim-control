# crapssim_control/templates.py
from typing import Dict, Any, List, Tuple, Optional
from .legalize import legalize_amount
from .eval import safe_eval

# BetIntent:
#   kind: "pass" | "dont_pass" | "field" | "place"
#   number: int | None
#   amount: int   (base/flat amount)
#   meta: dict    (optional fields: {"working": bool, "odds": int})
BetIntent = Tuple[str, Optional[int], int, Dict[str, Any]]

def _ev(expr, names: Dict[str, Any]) -> int | float | bool:
    if isinstance(expr, (int, float, bool)):
        return expr
    return safe_eval(str(expr), names)

def _ev_i(expr, names: Dict[str, Any]) -> int:
    return int(_ev(expr, names))

def _legal_amount(number: Optional[int], raw_amount: int, bubble: bool, table_level: int) -> int:
    return legalize_amount(number, raw_amount, bubble, table_level)

def _parse_simple_or_obj(value: Any) -> Dict[str, Any]:
    """
    Accept either a scalar (amount) or an object with fields like:
      {"amount": "...", "odds": "...", "working": false}
    Returns a normalized dict.
    """
    if isinstance(value, dict):
        return dict(value)
    return {"amount": value}

def render_template(template: Dict[str, Any],
                    vars_map: Dict[str, Any],
                    bubble: bool,
                    table_level: int) -> List[BetIntent]:
    """
    Convert a template dict into a list of bet intents with legalized amounts and optional meta.

    Supported top-level keys:
      - "pass", "dont_pass", "field": scalar or object with {"amount","odds","working"}
      - "place": { "6": expr|{amount,working}, "8": ..., ... }

    Notes (v0):
      - Odds amounts are passed through as int(expr) (no legalization yet).
      - "working" defaults to True unless explicitly set false on that bet.
    """
    out: List[BetIntent] = []

    # ---- Flat bets: pass / dp / field ----
    for flat_key in ("pass", "dont_pass", "field"):
        if flat_key in template:
            spec = _parse_simple_or_obj(template[flat_key])
            raw = _ev_i(spec.get("amount", 0), vars_map)
            amt = _legal_amount(None, raw, bubble, table_level)
            meta: Dict[str, Any] = {}
            if "working" in spec:
                meta["working"] = bool(spec["working"])
            if "odds" in spec:
                # For now, odds are not "legalized" -- just int-evaluated.
                # (In future we can add per-point odds steps/ratios if needed.)
                meta["odds"] = _ev_i(spec["odds"], vars_map)
            out.append((flat_key, None, amt, meta))

    # ---- Place bets ----
    if "place" in template:
        place_map = template["place"] or {}
        for k, v in place_map.items():
            n = int(k)
            spec = _parse_simple_or_obj(v)
            raw = _ev_i(spec.get("amount", 0), vars_map)
            amt = _legal_amount(n, raw, bubble, table_level)
            meta: Dict[str, Any] = {}
            if "working" in spec:
                meta["working"] = bool(spec["working"])
            out.append(("place", n, amt, meta))

    return out