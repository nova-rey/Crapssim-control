import csv
import pathlib
from typing import Mapping, Optional

FIELDS = [
    "roll",
    "window",
    "rule_id",
    "when_expr",
    "evaluated_true",
    "applied",
    "reason",
    "bankroll",
    "point_on",
    "hand_id",
    "roll_in_hand",
]


class DecisionsTrace:
    def __init__(self, folder):
        path = pathlib.Path(folder) / "decisions.csv"
        self._fp = open(path, "w", newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._fp, fieldnames=FIELDS)
        self._w.writeheader()
        self._fp.flush()
        self._rows_written = 0
        self._closed = False

    @property
    def rows_written(self) -> int:
        return self._rows_written

    def write(self, row: dict):
        if self._closed:
            raise ValueError("DecisionsTrace is closed")
        self._w.writerow({k: row.get(k, "") for k in FIELDS})
        self._fp.flush()
        self._rows_written += 1

    def ensure_summary_row(self, summary: Optional[Mapping[str, object]] = None) -> None:
        """Ensure at least one data row exists, inserting a run_complete summary if needed."""
        if self._closed or self._rows_written > 0:
            return

        roll_value = ""
        bankroll_value = ""

        if isinstance(summary, Mapping):
            # Prefer explicit last_roll from summary payload, otherwise fall back to rolls count.
            last_roll = summary.get("last_roll")
            rolls = summary.get("rolls")
            bankroll = summary.get("final_bankroll")

            if last_roll not in (None, ""):
                roll_value = last_roll
            elif rolls not in (None, ""):
                roll_value = rolls

            if bankroll not in (None, ""):
                bankroll_value = bankroll

        try:
            self.write(
                {
                    "roll": roll_value,
                    "window": "run_complete",
                    "rule_id": "summary",
                    "when_expr": "true",
                    "evaluated_true": True,
                    "applied": False,
                    "reason": "RUN_COMPLETE",
                    "bankroll": bankroll_value,
                    "point_on": "",
                    "hand_id": "",
                    "roll_in_hand": "",
                }
            )
        except Exception:
            # Fail open; an empty decisions.csv is preferable to raising during finalization.
            pass

    def close(self):
        if self._closed:
            return
        try:
            if self._rows_written == 0:
                self.ensure_summary_row()
            self._fp.flush()
        finally:
            self._fp.close()
            self._closed = True
