import json
import pathlib

import pytest

from crapssim_control.engine_adapter import CrapsSimAdapter

crapssim = pytest.importorskip("crapssim")


@pytest.fixture()
def live_engine_adapter():
    adapter = CrapsSimAdapter()
    adapter.start_session({})
    return adapter


@pytest.mark.parametrize("example", [
    "examples/example_line_odds.json",
    "examples/example_field_hardway.json",
    "examples/example_props.json",
    "examples/example_ats.json"
])
def test_examples_load_clean(example):
    path = pathlib.Path(example)
    spec = json.loads(path.read_text())
    assert "actions" in spec


def test_example_replay_consistency(live_engine_adapter):
    # Run example twice with same seed and compare summary digests
    a = live_engine_adapter
    a.start_session({"seed": 123})
    res1 = a.step_roll(dice=(3, 4))
    a.start_session({"seed": 123})
    res2 = a.step_roll(dice=(3, 4))
    assert res1["bankroll"] == res2["bankroll"]
    assert isinstance(res1.get("bets"), dict)
    assert isinstance(res2.get("bets"), dict)


def test_docs_schema_tags_present():
    text = pathlib.Path("docs/engine_contract.md").read_text()
    for tag in ["Snapshot", "Roll Event", "Capabilities", "Error Surface", "Replay"]:
        assert tag in text
