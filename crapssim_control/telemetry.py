from __future__ import annotations

import csv
import os
from typing import Optional, Dict, Any


class Telemetry:
    """
    Lightweight CSV logger that can be fully disabled.

    Usage:
      - Telemetry(csv_path=None)  -> disabled, no I/O (safe for tests)
      - Telemetry(csv_path="telemetry.csv") -> enabled CSV logging
    """

    def __init__(self, csv_path: Optional[str]) -> None:
        self.csv_path = csv_path
        self.enabled = bool(csv_path)

        # If disabled, do nothing else.
        if not self.enabled:
            return

        # Ensure directory exists
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)

        # Create header if file is new/empty
        if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
            with open(csv_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["event", "detail"])
                w.writeheader()

    def record_tick(self, event: Dict[str, Any], intents: Dict[str, Any], vs: Any) -> None:
        """
        Called once per roll by ControlStrategy. Safe no-op when disabled.
        """
        if not self.enabled:
            return

        row = {
            "event": event.get("event"),
            "detail": repr({"event": event, "intents": intents}),
        }
        try:
            with open(self.csv_path, "a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["event", "detail"])
                w.writerow(row)
        except Exception:
            # Never let telemetry break the sim.
            pass