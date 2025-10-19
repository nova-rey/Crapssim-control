# crapssim_control/telemetry.py
from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, List, Optional

class Telemetry:
    """
    CSV logger for crapssim-control. Write one row per event/tick so you can chart in Excel.
    """
    def __init__(self, csv_path: str, *, include_vars: bool = True):
        self.csv_path = csv_path
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        self.include_vars = include_vars
        self._f = open(self.csv_path, "w", newline="")
        self._w = csv.DictWriter(self._f, fieldnames=[
            "hand_id","shooter_id","roll_index",
            "event","dice_total","die1","die2",
            "phase","point",
            "bankroll","delta","cum_pnl",
            "mode","vars_json","intents_json"
        ])
        self._w.writeheader()
        self._cum_pnl = 0

    def log_tick(
        self,
        *,
        event: Dict[str, Any],
        table_state: Dict[str, Any],
        bankroll: Optional[float],
        bankroll_delta: Optional[float],
        mode: Optional[str],
        vars_snapshot: Optional[Dict[str, Any]],
        intents: List[Any]
    ):
        # roll up cum pnl
        d = float(bankroll_delta or 0.0)
        self._cum_pnl += d

        # unpack helpers
        dice = event.get("dice") or table_state.get("dice") or (None, None)
        die1, die2 = (dice + (None, None))[:2] if isinstance(dice, (list, tuple)) else (None, None)
        row = {
            "hand_id": table_state.get("hand_id"),
            "shooter_id": table_state.get("shooter_id"),
            "roll_index": table_state.get("roll_index"),
            "event": event.get("event"),
            "dice_total": event.get("total") or (die1 + die2 if die1 and die2 else None),
            "die1": die1,
            "die2": die2,
            "phase": table_state.get("phase"),          # "comeout" | "point"
            "point": table_state.get("point"),
            "bankroll": bankroll,
            "delta": d if d != 0 else None,
            "cum_pnl": self._cum_pnl,
            "mode": mode,
            "vars_json": json.dumps(vars_snapshot or {}) if self.include_vars else None,
            "intents_json": json.dumps(intents or []),
        }
        self._w.writerow(row)

    def close(self):
        try:
            self._f.flush()
            self._f.close()
        except Exception:
            pass

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): self.close()