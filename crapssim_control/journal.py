"""Utilities for effect summary serialization and normalization."""

from __future__ import annotations

from typing import Dict, Any
import json
import os
from datetime import datetime

EFFECT_KEYS_ORDER = (
    "schema",
    "verb",
    "target",
    "bets",
    "bets_delta",
    "bankroll_delta",
    "policy",
    "one_roll",
    "error",
    "meta",
)


def normalize_effect_summary(eff: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(eff or {})
    out.setdefault("schema", "1.0")
    # robust inference for verb if missing
    verb = out.get("verb")
    if not verb:
        meta = out.get("meta") if isinstance(out.get("meta"), dict) else {}
        verb = meta.get("verb") or meta.get("action") or "unknown"
        out["verb"] = verb
    out.setdefault("target", {})
    out.setdefault("bets", {})
    out.setdefault("bankroll_delta", 0.0)
    out.setdefault("policy", None)
    return out


def dumps_effect_summary_line(eff: Dict[str, Any]) -> str:
    eff = normalize_effect_summary(eff)
    ordered = {k: eff.get(k, None) for k in EFFECT_KEYS_ORDER if k in eff or k in ("verb","schema")}
    # append other keys in sorted order for stability
    extras = {k: v for k, v in eff.items() if k not in ordered}
    for k in sorted(extras.keys()):
        ordered[k] = extras[k]
    return json.dumps(ordered, separators=(",", ":"), ensure_ascii=False)


def _write_line(line: Dict[str, Any], *, path: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    if line.get("event") == "rejected_effect":
        payload = json.dumps(line, separators=(",", ":"), ensure_ascii=False)
    else:
        payload = dumps_effect_summary_line(line)
    with open(path, "a", encoding="utf-8") as f:
        f.write(payload + "\n")


def append_effect_summary_line(effect: Dict[str, Any], *, path: str) -> None:
    if effect.get("rejected"):
        line = {
            "event": "rejected_effect",
            "code": effect.get("code"),
            "reason": effect.get("reason"),
            "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        }
    else:
        line = effect

    _write_line(line, path=path)
