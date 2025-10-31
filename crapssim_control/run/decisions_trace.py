import csv
import pathlib

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

    @property
    def rows_written(self) -> int:
        return self._rows_written

    def write(self, row: dict):
        self._w.writerow({k: row.get(k, "") for k in FIELDS})
        self._fp.flush()
        self._rows_written += 1

    def close(self):
        try:
            self._fp.flush()
        finally:
            self._fp.close()
