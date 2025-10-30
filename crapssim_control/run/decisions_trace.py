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

    def write(self, row: dict):
        self._w.writerow({k: row.get(k, "") for k in FIELDS})

    def close(self):
        self._fp.close()
