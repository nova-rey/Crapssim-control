import csv
import json
import os
from pathlib import Path

from crapssim_control.reporting import parse_journal_csv, compute_report_v2
from crapssim_control.report_hook import maybe_enrich_report


def _write_csv(path, rows, fieldnames):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def _toy_journal():
    # Hand 1: establish then PSO
    # Hand 2: establish, intermediate roll, then made point
    rows = []
    rows.append({"roll_index":0,"hand_id":1,"roll_in_hand":1,"point_on":0,"bankroll_after":1000,"hand_result":"","point_state":"established","established_flag":1,"made_flag":0,"seven_out_flag":0})
    rows.append({"roll_index":1,"hand_id":1,"roll_in_hand":2,"point_on":1,"bankroll_after":990,"hand_result":"loss","point_state":"seven_out","established_flag":0,"made_flag":0,"seven_out_flag":1})
    rows.append({"roll_index":2,"hand_id":2,"roll_in_hand":1,"point_on":0,"bankroll_after":1000,"hand_result":"","point_state":"established","established_flag":1,"made_flag":0,"seven_out_flag":0})
    rows.append({"roll_index":3,"hand_id":2,"roll_in_hand":2,"point_on":1,"bankroll_after":1010,"hand_result":"","point_state":"","established_flag":0,"made_flag":0,"seven_out_flag":0})
    rows.append({"roll_index":4,"hand_id":2,"roll_in_hand":3,"point_on":1,"bankroll_after":1025,"hand_result":"win","point_state":"made","established_flag":0,"made_flag":1,"seven_out_flag":0})
    fns = ["roll_index","hand_id","roll_in_hand","point_on","bankroll_after","hand_result","point_state","established_flag","made_flag","seven_out_flag"]
    return fns, rows


def test_compute_report_v2_metrics(tmp_path):
    fns, rows = _toy_journal()
    csv_path = tmp_path / "journal.csv"
    _write_csv(csv_path, rows, fns)
    parsed = parse_journal_csv(str(csv_path))
    rep = compute_report_v2(parsed, bankroll_start=1000, bet_family_digest=[
        {"name":"pass_line","net":85,"wagered":640,"wins":2,"losses":1},
        {"name":"place_6_8","net":55,"wagered":980,"wins":1,"losses":1},
    ])
    assert rep["identity"]["report_schema_version"] == "2.0"
    assert rep["summary"]["hands_played"] == 2
    assert rep["summary"]["rolls"] == 5
    assert rep["summary"]["pso_count"] == 1
    assert rep["point_cycle"]["established"] == 2
    assert rep["point_cycle"]["made"] == 1
    assert rep["point_cycle"]["seven_outs"] == 1
    assert rep["point_cycle"]["pso_rate"] == 0.5
    assert rep["by_bet_family"]["top_name"] == "pass_line"


def test_report_hook_enriches_artifacts(tmp_path):
    art = tmp_path / "exports" / "RUN1"
    art.mkdir(parents=True, exist_ok=True)
    fns, rows = _toy_journal()
    _write_csv(art / "journal.csv", rows, fns)
    _write_json(art / "report.json", {
        "identity": {"run_id": "RUN1", "engine_version": "eng-x", "csc_version": "csc-y"},
        "summary": {"bankroll_start": 1000}
    })
    _write_json(art / "manifest.json", {"run_id": "RUN1", "engine_version": "eng-x", "csc_version": "csc-y"})

    ok = maybe_enrich_report(str(art))
    assert ok is True

    enriched = json.loads((art / "report.json").read_text("utf-8"))
    assert enriched["identity"]["run_id"] == "RUN1"
    assert enriched["identity"]["report_schema_version"] == "2.0"
    assert isinstance(enriched["summary"]["pso_count"], int)
    assert "max_drawdown" in enriched["summary"]
    assert "point_on_time_pct" in enriched["summary"]
