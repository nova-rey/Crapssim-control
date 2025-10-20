"""Utilities for effect summary serialization and normalization."""

from __future__ import annotations

from typing import Any, Dict
import json

EFFECT_KEYS_ORDER = (
    "schema",
    "verb",
    "target",
    "bets",
    "bankroll_delta",
    "policy",
    "error",
    "meta",
)


def normalize_effect_summary(eff: Dict[str, Any] | None) -> Dict[str, Any]:
    """Return a copy with required keys present and 'verb' guaranteed."""
    out: Dict[str, Any] = dict(eff or {})
    out.setdefault("schema", "1.0")
    if "verb" not in out or out.get("verb") in (None, ""):
        meta = out.get("meta")
        verb_val: Any = None
        if isinstance(meta, dict):
            verb_val = meta.get("verb")
        out["verb"] = verb_val if isinstance(verb_val, str) and verb_val else "unknown"
    out.setdefault("target", {})
    out.setdefault("bets", {})
    out.setdefault("bankroll_delta", 0.0)
    out.setdefault("policy", None)
    return out


def dumps_effect_summary_line(eff: Dict[str, Any] | None) -> str:
    """JSON line with predictable key order for diffs/log parsing."""
    normalized = normalize_effect_summary(eff or {})
    ordered: Dict[str, Any] = {
        key: normalized.get(key, None)
        for key in EFFECT_KEYS_ORDER
        if key in normalized or key in ("verb", "schema")
    }
    extras = {k: v for k, v in normalized.items() if k not in ordered}
    for key in sorted(extras):
        ordered[key] = extras[key]
    return json.dumps(ordered, separators=(",", ":"), ensure_ascii=False)
