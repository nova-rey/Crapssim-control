import pytest

from crapssim_control.engine_adapter import VanillaAdapter


def mk(spec=None):
    a = VanillaAdapter()
    a.start_session(spec or {"run": {"journal": {"explain": True, "explain_grouping": "first_only"}}})
    return a


def test_grouped_first_only(monkeypatch):
    lines = []
    from crapssim_control import journal as J

    monkeypatch.setattr(J, "_write_line", lambda line, **k: lines.append(line))
    a = mk()
    a.apply_actions(
        [
            {"verb": "place_bet", "args": {"number": 6, "amount": 12}},
            {"verb": "place_bet", "args": {"number": 8, "amount": 12}},
        ],
        why="Placed 6 and 8 because point is established.",
        group_id="testgrp",
    )
    whys = [l.get("why", "") for l in lines if isinstance(l, dict)]
    assert any("Placed 6 and 8" in w for w in whys)
    assert whys.count("") >= 1


def test_grouped_ditto(monkeypatch):
    lines = []
    from crapssim_control import journal as J

    monkeypatch.setattr(J, "_write_line", lambda line, **k: lines.append(line))
    a = mk({"run": {"journal": {"explain": True, "explain_grouping": "ditto"}}})
    a.apply_actions(
        [
            {"verb": "place_bet", "args": {"number": 6, "amount": 12}},
            {"verb": "place_bet", "args": {"number": 8, "amount": 12}},
        ],
        why="Placed 6 and 8 because point is established.",
        group_id="testgrp2",
    )
    whys = [l.get("why", "") for l in lines if isinstance(l, dict)]
    assert "〃" in whys


def test_aggregate_line(monkeypatch):
    lines = []
    from crapssim_control import journal as J

    monkeypatch.setattr(J, "_write_line", lambda line, **k: lines.append(line))
    a = mk({"run": {"journal": {"explain": True, "explain_grouping": "aggregate_line"}}})
    a.apply_actions(
        [
            {"verb": "place_bet", "args": {"number": 6, "amount": 12}},
            {"verb": "place_bet", "args": {"number": 8, "amount": 12}},
        ],
        why="Placed 6 and 8 because point is established.",
        group_id="testgrp3",
    )
    assert any((l.get("event") == "group_explain") for l in lines if isinstance(l, dict))
