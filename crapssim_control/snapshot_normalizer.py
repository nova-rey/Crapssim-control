"""Snapshot normalization helpers for live-engine integration."""

from __future__ import annotations

from typing import Any, Dict, Mapping


class SnapshotNormalizer:
    """Augment raw engine snapshots with CSC-friendly bet keys."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def _base_normalize(self, raw: Mapping[str, Any] | None) -> Dict[str, Any]:
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        return dict(raw.items())

    def normalize_snapshot(self, raw: Mapping[str, Any] | None) -> Dict[str, Any]:
        snap = self._base_normalize(raw)
        bets = snap.setdefault("bets", {})
        if not isinstance(bets, dict):
            bets = {}
            snap["bets"] = bets

        table = getattr(self.engine, "table", None)
        if not table:
            return snap

        field_amount = getattr(table, "field_bet", None)
        if field_amount is not None:
            try:
                bets["field"] = float(field_amount)
            except (TypeError, ValueError):
                bets.setdefault("field", 0.0)
        else:
            bets.setdefault("field", bets.get("field", 0.0))

        for number in (4, 6, 8, 10):
            key = f"hardway_{number}"
            raw_value = getattr(table, key, None)
            if raw_value is not None:
                try:
                    bets[key] = float(raw_value)
                except (TypeError, ValueError):
                    bets.setdefault(key, bets.get(key, 0.0))
            else:
                bets.setdefault(key, bets.get(key, 0.0))

        for side in ("come", "dc"):
            for number in (4, 5, 6, 8, 9, 10):
                key = f"odds_{side}_{number}"
                raw_value = getattr(table, key, None)
                if raw_value is not None:
                    try:
                        bets[key] = float(raw_value)
                    except (TypeError, ValueError):
                        bets.setdefault(key, bets.get(key, 0.0))
                else:
                    bets.setdefault(key, bets.get(key, 0.0))

        return snap
