import csv
import io
from types import SimpleNamespace

from crapssim_control.csv_journal import _append_adapter_snapshot_fields_if_enabled


def test_csv_has_no_adapter_fields_when_adapter_off():
    controller = SimpleNamespace(adapter=None)
    fieldnames = ["roll_id"]
    row = {"roll_id": 1}

    _append_adapter_snapshot_fields_if_enabled(controller, row, fieldnames)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow(row)
    buffer.seek(0)
    output = buffer.read()

    assert "bankroll_after" not in output
    assert fieldnames == ["roll_id"]
