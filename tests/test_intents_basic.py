# tests/test_intents_basic.py
from crapssim_control.tracker import Tracker
from crapssim_control.tracker_ledger_shim import wire_ledger

def make_tracker():
    t = Tracker()
    wire_ledger(t)
    return t

def test_intent_create_match_and_cancel():
    t = make_tracker()

    # Create an intent to place 6 for $30
    iid = t.on_intent_created({"bet": "place", "number": 6, "stake": 30.0})
    assert isinstance(iid, int)

    # Place the bet and ensure it links to the intent (implicit match by bet+number)
    t.on_bet_placed({"bet": "place", "amount": 30.0, "number": 6})
    snap = t.snapshot()
    intents = snap["ledger"]["intents"]
    assert intents["open_count"] == 0
    assert intents["matched_count"] == 1

    # Create then cancel another intent
    iid2 = t.on_intent_created({"bet": "place", "number": 8, "stake": 30.0})
    t.on_intent_canceled(iid2, reason="strategy_changed")
    snap2 = t.snapshot()
    intents2 = snap2["ledger"]["intents"]
    assert intents2["canceled_count"] == 1

def test_intent_with_explicit_id_passthrough():
    t = make_tracker()
    iid = t.on_intent_created({"bet": "odds", "number": 5, "stake": 20.0})
    # Explicitly attach the id on placement
    t.on_bet_placed({"bet": "odds", "amount": 20.0, "number": 5, "intent_id": iid})
    snap = t.snapshot()
    assert snap["ledger"]["intents"]["matched_count"] == 1