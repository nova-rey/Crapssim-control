"""
Decision Journal & Safeties (v1)
Records all rule/action events with cooldown and scope protections.
"""

import json
import time
from typing import Any, Dict, Tuple


class DecisionJournal:
    def __init__(self, path="decision_journal.jsonl"):
        self.path = path
        self.cooldowns: Dict[str, int] = {}
        self.scope_flags = set()

    # --- SAFETIES ------------------------------------------------------------

    def can_fire(self, rule_id: str, scope: str, cooldown: int) -> Tuple[bool, str]:
        """Check if a rule can fire based on scope or cooldown."""
        if rule_id in self.scope_flags:
            return False, "scope_locked"
        cd = self.cooldowns.get(rule_id, 0)
        if cd > 0:
            return False, f"cooldown_{cd}"
        return True, "ok"

    def apply_fire(self, rule_id: str, scope: str, cooldown: int):
        """Apply cooldown and scope flags after a rule fires."""
        if scope and scope != "roll":
            self.scope_flags.add(rule_id)
        if cooldown:
            self.cooldowns[rule_id] = cooldown

    def tick(self):
        """Decrement cooldowns each roll."""
        for k in list(self.cooldowns.keys()):
            self.cooldowns[k] = max(0, self.cooldowns[k] - 1)

    # --- LOGGING -------------------------------------------------------------

    def record(self, entry: Dict[str, Any]):
        """Append a decision record as JSON."""
        entry.setdefault("timestamp", time.time())
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # --- HELPER --------------------------------------------------------------

    def to_csv(self, csv_path: str):
        """Optional export to CSV for analysis."""
        import csv

        with open(self.path, "r", encoding="utf-8") as src, open(
            csv_path, "w", newline="", encoding="utf-8"
        ) as dest:
            writer = csv.DictWriter(dest, fieldnames=list(json.loads(src.readline()).keys()))
            src.seek(0)
            writer.writeheader()
            for line in src:
                writer.writerow(json.loads(line))
