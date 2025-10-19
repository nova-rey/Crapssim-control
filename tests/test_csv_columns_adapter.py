import csv
import io

from crapssim_control.engine_adapter import VanillaAdapter


def test_csv_includes_new_columns():
    v = VanillaAdapter()
    v.apply_action("press_and_collect", {})
    snap = v.snapshot_state()
    fieldnames = ["roll_id", "bankroll_after", "bet_6", "bet_8"]
    data = {
        "roll_id": 1,
        "bankroll_after": snap["bankroll"],
        "bet_6": snap["bets"]["6"],
        "bet_8": snap["bets"]["8"],
    }
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow(data)
    output.seek(0)
    text = output.read()
    assert "bankroll_after" in text
    assert "bet_6" in text
    assert "bet_8" in text
