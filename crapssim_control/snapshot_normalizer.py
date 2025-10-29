"""Snapshot normalization helpers for live-engine integration."""

from __future__ import annotations

from typing import Any, Dict, Mapping, List


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

        def _prop_intents(source: Any) -> List[Mapping[str, Any]]:
            if source is None:
                return []
            candidates: List[Any] = []
            try:
                strategy = getattr(source, "_strategy", None)
            except Exception:
                strategy = None
            if strategy is not None:
                candidates.append(strategy)
            candidates.append(source)

        for candidate in candidates:
            if candidate is None:
                continue
            try:
                intents = getattr(candidate, "_props_intent", None)
            except Exception:
                intents = None
            if intents:
                try:
                    return list(intents)
                except Exception:
                    continue
        try:
            pending = getattr(source, "_csc_props_pending", None)
        except Exception:
            pending = None
        if pending:
            try:
                return list(pending)
            except Exception:
                pass
        adapter_ref = getattr(source, "_csc_adapter_ref", None)
        if adapter_ref is not None:
            try:
                pending = getattr(adapter_ref, "_props_pending", None)
                if pending:
                    return list(pending)
            except Exception:
                return []
        return []

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

        props_bucket = snap.get("props")
        if not isinstance(props_bucket, dict):
            props_bucket = {}
            snap["props"] = props_bucket
        player = None
        get_player = getattr(self.engine, "_cs_get_player", None)
        if callable(get_player):
            try:
                player = get_player()
            except Exception:
                player = None
        intents = _prop_intents(player)
        if intents:
            props_bucket.clear()
            for intent in intents[-8:]:
                if not isinstance(intent, Mapping):
                    continue
                fam = str(intent.get("prop_family", intent.get("family", "prop")))
                key = fam
                if fam == "hop":
                    combo = intent.get("combo", "")
                    key = f"hop_{combo}" if combo else "hop"
                try:
                    amt = float(intent.get("amount", 0.0) or 0.0)
                except (TypeError, ValueError):
                    amt = 0.0
                props_bucket[key] = amt

        ats_keys = ("small", "tall", "all")
        progress: Dict[str, float] = {k: 0.0 for k in ats_keys}
        raw_progress = None
        if player is not None:
            raw_progress = getattr(player, "_ats_progress", None)
        if raw_progress is None:
            raw_progress = getattr(self.engine, "_ats_progress", None)
        if isinstance(raw_progress, Mapping):
            for key in ats_keys:
                value = raw_progress.get(key, 0)
                try:
                    progress[key] = float(value)
                except (TypeError, ValueError):
                    progress[key] = 0.0
        for key in ats_keys:
            bets[f"ats_{key}"] = progress.get(key, 0.0)
        snap["ats_progress"] = {k: progress.get(k, 0.0) for k in ats_keys}

        dice_val = snap.get("dice")
        total_val = snap.get("total")
        last_roll: Dict[str, Any] = {}
        if isinstance(dice_val, (list, tuple)) and len(dice_val) == 2:
            try:
                last_roll["dice"] = (int(dice_val[0]), int(dice_val[1]))
            except Exception:
                pass
        if isinstance(total_val, (int, float)):
            try:
                last_roll["total"] = int(total_val)
            except Exception:
                pass
        snap["last_roll"] = last_roll if last_roll else {}

        return snap
