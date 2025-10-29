import csv
from pathlib import Path

from crapssim_control.csv_journal import CSVJournal
from tests import skip_csv_preamble


def test_csv_extra_enrichment(tmp_path: Path):
    p = tmp_path / "journal.csv"
    j = CSVJournal(str(p), append=True, run_id="t1", seed=123)

    snapshot = {
        "event_type": "roll",
        "point": 6,
        "rolls_since_point": 2,
        "on_comeout": False,
        "mode": "Main",
        "units": 10,
        "bankroll": 500,
        "roll": 8,
        "event_point": 6,
        "extra": {"hint": "ok"},
    }

    actions = [
        {
            "source": "rule",
            "id": "rule:#1",
            "action": "set",
            "bet_type": "place_8",
            "amount": 12,
            "notes": "x",
            "seq": 1,
        },
        {
            "source": "template",
            "id": "template:Main",
            "action": "clear",
            "bet_type": "place_6",
            "amount": None,
            "notes": "",
            "seq": 2,
        },
    ]

    n = j.write_actions(actions, snapshot=snapshot)
    assert n == 2
    assert p.exists()

    with open(p, newline="", encoding="utf-8") as fh:
        skip_csv_preamble(fh)
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    # schema columns still present
    for col in [
        "ts",
        "run_id",
        "seed",
        "event_type",
        "point",
        "rolls_since_point",
        "on_comeout",
        "mode",
        "units",
        "bankroll",
        "source",
        "id",
        "action",
        "bet_type",
        "amount",
        "notes",
        "extra",
    ]:
        assert col in rows[0]

    # extra contains merged info
    import json

    e0 = json.loads(rows[0]["extra"])
    assert e0.get("hint") == "ok"
    assert e0.get("roll") == 8
    assert e0.get("event_point") == 6
    assert e0.get("seq") == 1
