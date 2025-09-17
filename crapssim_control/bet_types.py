"""
bet_types.py -- Batch 9
Canonicalization helpers for bet types so analytics don't fragment.

Public API:
    normalize_bet_type(raw: str, meta: dict | None = None) -> str
    extract_number(meta: dict | None) -> int | None
"""

from __future__ import annotations
from typing import Optional, Dict, Any
import re

# Simple alias table → canonical
_ALIASES = {
    # Line / come families
    "pass": "pass_line",
    "pass_line": "pass_line",
    "pl": "pass_line",
    "dont pass": "dont_pass",
    "don't pass": "dont_pass",
    "dp": "dont_pass",
    "come": "come",
    "dont come": "dont_come",
    "don't come": "dont_come",
    "dc": "dont_come",
    # Field / hardways
    "field": "field",
    "hard": "hardways",     # generic; number-aware mapping below
    "hardway": "hardways",
    "hardways": "hardways",
    # Odds (generic)
    "odds": "odds",
    "lay": "lay",
    # Place (generic)
    "place": "place",
}

_NUMBER_WORDS = {
    "four": 4, "five": 5, "six": 6, "eight": 8, "nine": 9, "ten": 10,
    "4": 4, "5": 5, "6": 6, "8": 8, "9": 9, "10": 10,
}

_HARD_ALLOWED = {4, 6, 8, 10}


def _clean(s: str) -> str:
    s = s.strip().lower()
    # normalize punctuation to spaces, then squeeze
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_number(meta: Optional[Dict[str, Any]] = None) -> Optional[int]:
    if not meta:
        return None
    for k in ("number", "point", "box", "target"):
        if k in meta and meta[k] is not None:
            try:
                return int(meta[k])
            except Exception:
                pass
    # fall back to scanning a 'name' or 'bet' string if present
    for k in ("bet_type", "bet", "name"):
        v = meta.get(k)
        if not isinstance(v, str):
            continue
        toks = _clean(v).split()
        for t in reversed(toks):
            if t in _NUMBER_WORDS:
                return _NUMBER_WORDS[t]
            try:
                n = int(t)
                if n in (4, 5, 6, 8, 9, 10):
                    return n
            except Exception:
                pass
    return None


def normalize_bet_type(raw: Optional[str], meta: Optional[Dict[str, Any]] = None) -> str:
    """
    Returns a canonical snake_case key.

    Examples:
      "Place 6" / "place_6" / "PL6"  → "place_6"
      "Come Odds 5" / "odds5 come"   → "odds_5_come"
      "Pass Line" / "pass" / "PL"    → "pass_line"
      "Don't Pass" / "dp"            → "dont_pass"
      "Hard 8" / "hardway 8"         → "hard_8"
      "Field"                         → "field"
      "Odds 5 (line)"                → "odds_5_line"
      "Lay 10"                        → "lay_10"
    """
    raw = raw or ""
    base = _clean(raw)

    # Quick alias wins
    if base in _ALIASES:
        canon = _ALIASES[base]
        if canon in ("place", "odds", "lay", "hardways"):
            # may be number-aware
            n = extract_number(meta)
            if canon == "place" and n:
                return f"place_{n}"
            if canon == "lay" and n:
                return f"lay_{n}"
            if canon == "odds":
                # try to classify odds context
                # prefer 'come' if mentioned, then 'line'
                if "come" in base or (isinstance(meta, dict) and str(meta.get("context","")).lower() == "come"):
                    return f"odds_{n}_come" if n else "odds"
                if "pass" in base or (isinstance(meta, dict) and "line" in str(meta.get("context","")).lower()):
                    return f"odds_{n}_line" if n else "odds"
                return f"odds_{n}" if n else "odds"
            if canon == "hardways" and n in _HARD_ALLOWED:
                return f"hard_{n}"
            return canon
        return canon

    toks = base.split()

    # Hardways (number-aware)
    if "hard" in toks or "hardways" in toks or "hardway" in toks:
        n = extract_number({"bet": raw, **(meta or {})})
        if n in _HARD_ALLOWED:
            return f"hard_{n}"
        return "hardways"

    # Field
    if "field" in toks:
        return "field"

    # Pass / don't pass
    if "pass" in toks and ("dont" in toks or "don" in toks):  # "don't" normalized to "don t" -> catch "don"
        return "dont_pass"
    if "pass" in toks:
        return "pass_line"

    # Come / don't come
    if "come" in toks and ("dont" in toks or "don" in toks):
        return "dont_come"
    if "come" in toks:
        # could be naked come bet OR odds on come (handled below with "odds")
        if "odds" not in toks:
            return "come"

    # Odds (context- & number-aware)
    if "odds" in toks:
        n = extract_number({"bet": raw, **(meta or {})})
        if "come" in toks:
            return f"odds_{n}_come" if n else "odds"
        if "pass" in toks or "line" in toks:
            return f"odds_{n}_line" if n else "odds"
        return f"odds_{n}" if n else "odds"

    # Lay
    if "lay" in toks:
        n = extract_number({"bet": raw, **(meta or {})})
        return f"lay_{n}" if n else "lay"

    # Place (number-aware)
    if "place" in toks:
        n = extract_number({"bet": raw, **(meta or {})})
        return f"place_{n}" if n else "place"

    # Lone number → interpret as place bet (most engines emit that for shortcuts)
    n = extract_number({"bet": raw, **(meta or {})})
    if n:
        return f"place_{n}"

    # Fallback to cleaned raw (snake-ish)
    return base.replace(" ", "_") or "unknown"