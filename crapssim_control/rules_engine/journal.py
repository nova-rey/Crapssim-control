"""
Decision Journal & Safeties (v1)
Records all rule/action events with cooldown and scope protections.
"""

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from crapssim_control.engine_adapter import validate_effect_summary


@dataclass
class JournalWriter:
    """Helper for emitting normalized journal entries."""

    journal: "DecisionJournal"
    base_fields: Optional[Dict[str, Any]] = None

    def write(
        self,
        *,
        run_id: str,
        origin: str,
        action: str,
        args: Optional[Dict[str, Any]] = None,
        executed: bool = False,
        rejection_reason: Optional[str] = None,
        correlation_id: Optional[str] = None,
        timestamp: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
        **fields: Any,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.base_fields:
            payload.update(self.base_fields)
        if extra:
            payload.update(extra)
        payload.update(fields)
        payload["run_id"] = run_id
        payload["origin"] = origin
        payload["action"] = action
        payload["args"] = dict(args or {})
        payload["executed"] = bool(executed)
        if rejection_reason is not None:
            payload["rejection_reason"] = rejection_reason
        if correlation_id is not None:
            payload["correlation_id"] = correlation_id
        return self.journal.record(payload, timestamp=timestamp)


class DecisionJournal:
    def __init__(self, path="decision_journal.jsonl"):
        self.path = path
        self.cooldowns: Dict[str, int] = {}
        self.scope_flags = set()
        self._seq = 0
        self.entries: List[Dict[str, Any]] = []

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

    def record(
        self,
        entry: Dict[str, Any],
        *,
        timestamp: Optional[float] = None,
        controller: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Append a decision record as JSON."""
        normalized = dict(entry or {})
        self._seq += 1
        normalized["seq"] = self._seq
        if timestamp is None:
            timestamp = normalized.get("timestamp")
        if timestamp is None:
            timestamp = time.time()
        normalized["timestamp"] = float(timestamp)
        if controller and hasattr(controller, "adapter"):
            adapter = getattr(controller, "adapter", None)
            effect = getattr(adapter, "last_effect", None)
            if effect and "effect_summary" not in normalized:
                validate_effect_summary(effect, schema="1.0")
                normalized["effect_summary"] = effect
        origin = normalized.get("origin")
        normalized["origin"] = str(origin) if origin is not None else "unknown"
        action = normalized.get("action")
        normalized["action"] = str(action) if action is not None else "unknown"
        args = normalized.get("args")
        if isinstance(args, dict):
            normalized["args"] = args
        else:
            normalized["args"] = {}
        executed = normalized.get("executed")
        normalized["executed"] = bool(executed)
        if "rejection_reason" not in normalized or normalized["rejection_reason"] is None:
            normalized["rejection_reason"] = None
        else:
            normalized["rejection_reason"] = str(normalized["rejection_reason"])
        if "correlation_id" in normalized:
            corr = normalized["correlation_id"]
            normalized["correlation_id"] = str(corr) if corr is not None else None
        else:
            normalized["correlation_id"] = None
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(normalized) + "\n")
        if "effect_summary" not in normalized:
            normalized["effect_summary"] = None
        self.entries.append(normalized)
        return normalized

    def writer(self, base_fields: Optional[Dict[str, Any]] = None) -> JournalWriter:
        return JournalWriter(self, base_fields=base_fields)

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
