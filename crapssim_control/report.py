from __future__ import annotations

from typing import Any, Dict


def build_report(live_snapshot: dict, replay_snapshot: dict, meta: dict) -> Dict[str, Any]:
    report = {
        "effect_schema": "1.0",
        "meta": dict(meta),
        "live_snapshot": live_snapshot,
        "replay_snapshot": replay_snapshot,
        "replay_verified": (live_snapshot == replay_snapshot),
    }
    return report
