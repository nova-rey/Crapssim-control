# tests/test_exports_basic.py
import os
import json

from crapssim_control.tracker import Tracker
from crapssim_control.tracker_ledger_shim import wire_ledger
from crapssim_control.bet_attrib import attach_bet_attrib
from crapssim_control.tracker_histograms import attach_histograms

from crapssim_control.exports import (
    export_session_json,
    export_ledger_csv,
    export_intents_csv,
    export_bet_attrib_csv,
    export_histograms_csv,
)


def _make_tracker():
    t = Tracker({"enabled": True})
    wire_ledger(t)
    attach_bet_attrib(t, enabled=True)
    attach_histograms(t, enabled=True)
    # seed some data
    t.on_intent_created({"bet": "place", "number": 6, "stake": 30})
    t.on_bet_placed({"bet": "place", "amount": 30, "number": 6})
    t.on_roll(6)  # accrue exposure
    t.on_bet_resolved({"bet": "place", "amount": 30, "payout": 37, "number": 6, "outcome": "win"})
    t.on_roll(8)
    t.on_bet_resolved({"bet_type": "field", "stake": 5, "outcome": "loss"})
    return t


def test_export_session_json(tmp_path):
    t = _make_tracker()
    p = tmp_path / "session.json"
    export_session_json(t, str(p))
    assert p.exists() and p.stat().st_size > 0
    data = json.loads(p.read_text())
    assert "ledger" in data and "bet_attrib" in data


def test_export_csvs(tmp_path):
    t = _make_tracker()

    p1 = tmp_path / "ledger.csv"
    p2 = tmp_path / "intents.csv"
    p3 = tmp_path / "bet_attrib.csv"
    p4 = tmp_path / "hist.csv"

    export_ledger_csv(t, str(p1))
    export_intents_csv(t, str(p2))
    export_bet_attrib_csv(t, str(p3))
    export_histograms_csv(t, str(p4))

    for p in (p1, p2, p3, p4):
        assert p.exists() and p.stat().st_size > 0

    # Quick sanity: header presence
    header = p3.read_text().splitlines()[0]
    assert "bet_type" in header and "roi" in header