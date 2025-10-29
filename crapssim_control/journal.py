"""Utilities for effect summary serialization and normalization."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import json
import os

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


_group_state: Dict[str, Any] = {"written": set()}


def reset_group_state() -> None:
    """Reset per-run explain grouping state."""

    _group_state["written"] = set()


def _format_why_for_row(why: str, grouping: str, is_first: bool) -> str:
    if not why:
        return ""
    if grouping == "first_only":
        return why if is_first else ""
    if grouping == "ditto":
        return why if is_first else "〃"
    if grouping == "aggregate_line":
        return ""
    return why if is_first else ""


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


def dumps_effect_summary_line(
    effect: Dict[str, Any], *, explain_opts: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Normalize an effect row and attach optional explain metadata."""

    explain = explain_opts or {}
    line = normalize_effect_summary(effect)
    why = line.pop("_why", "") or line.pop("why", "")
    group_id = line.pop("_why_group", None)
    grouping = str(explain.get("explain_grouping", "first_only"))

    is_first = True
    track_group = True
    if grouping == "aggregate_line" and line.get("event") != "group_explain":
        track_group = False
    if group_id:
        seen: set[str] = _group_state.setdefault("written", set())  # type: ignore[assignment]
        if track_group:
            is_first = group_id not in seen
            if is_first:
                seen.add(group_id)
        else:
            is_first = group_id not in seen

    if explain.get("explain"):
        line["why"] = _format_why_for_row(str(why), grouping, is_first)

    line.setdefault("timestamp", datetime.utcnow().isoformat(timespec="seconds"))
    return line


def _serialize_line(line: Dict[str, Any]) -> str:
    ordered = {
        k: line.get(k, None) for k in EFFECT_KEYS_ORDER if k in line or k in ("verb", "schema")
    }
    extras = {k: v for k, v in line.items() if k not in ordered}
    for key in sorted(extras.keys()):
        ordered[key] = extras[key]
    return json.dumps(ordered, separators=(",", ":"), ensure_ascii=False)


def _write_line(line: Dict[str, Any], *, path: Optional[str]) -> None:
    if path is None:
        return
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    if line.get("event") == "rejected_effect":
        payload = json.dumps(line, separators=(",", ":"), ensure_ascii=False)
    else:
        payload = _serialize_line(line)
    with open(path, "a", encoding="utf-8") as f:
        f.write(payload + "\n")


def append_effect_summary_line(
    effect: Dict[str, Any], *, path: Optional[str], explain_opts: Optional[Dict[str, Any]] = None
) -> None:
    if effect.get("rejected"):
        line = {
            "event": "rejected_effect",
            "code": effect.get("code"),
            "reason": effect.get("reason"),
            "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        }
    else:
        line = dumps_effect_summary_line(effect, explain_opts=explain_opts)

    _write_line(line, path=path)
