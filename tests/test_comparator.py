import json
import os
from pathlib import Path
import zipfile

from csc.comparator import make_leaderboard, make_comparisons
from csc.aggregator import aggregate


def _write_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")


def test_make_leaderboard_sorted_and_tiebreak():
    rows = [
        {"run_id": "B", "ROI": 0.10, "bankroll_final": 1100, "max_drawdown": 80, "hands": 50, "rolls": 250},
        {"run_id": "A", "ROI": 0.10, "bankroll_final": 1110, "max_drawdown": 70, "hands": 51, "rolls": 252},
        {"run_id": "C", "ROI": -0.05, "bankroll_final": 950, "max_drawdown": 150, "hands": 48, "rolls": 240},
        {"run_id": "D", "ROI": None},
    ]
    lb = make_leaderboard(rows, "ROI", top_k=3)
    assert [r["run_id"] for r in lb] == ["A", "B", "C"]  # tie break by run_id


def test_make_comparisons_deltas_and_ratios():
    rows = [
        {"run_id": "X", "ROI": 0.20, "bankroll_final": 1200, "max_drawdown": 90},
        {"run_id": "Y", "ROI": 0.15, "bankroll_final": 1150, "max_drawdown": 100},
        {"run_id": "Z", "ROI": -0.10, "bankroll_final": 900, "max_drawdown": 200},
    ]
    comps = make_comparisons(rows, "ROI")
    assert comps["top_run"] == "X"
    # Y vs X
    y = next(c for c in comps["comparisons"] if c["run_id"] == "Y")
    assert abs(y["delta_ROI"] - (0.15 - 0.20)) < 1e-12
    assert abs(y["relative_efficiency"] - 0.75) < 1e-12
    # Z vs X
    z = next(c for c in comps["comparisons"] if c["run_id"] == "Z")
    assert abs(z["delta_bankroll_final"] - (900 - 1200)) < 1e-12


def test_aggregate_writes_leaderboard_and_comparisons(tmp_path):
    out_dir = tmp_path / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Create a minimal batch_manifest with two success items and artifact reports
    run1_dir = out_dir / "RUN1"
    run1_dir.mkdir()
    _write_json(
        run1_dir / "report.json",
        {
            "summary": {
                "bankroll_start": 1000,
                "bankroll_final": 1200,
                "hands_played": 60,
                "rolls": 300,
                "max_drawdown": 90,
                "pso_count": 2,
                "points_made": 15,
            },
            "by_bet_family": {"top_name": "pass_line"},
        },
    )
    # Second as zip with artifacts/report.json
    out_zip = out_dir / "RUN2.zip"
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        payload = json.dumps(
            {
                "summary": {
                    "bankroll_start": 1000,
                    "bankroll_final": 900,
                    "hands_played": 55,
                    "rolls": 280,
                    "max_drawdown": 150,
                    "pso_count": 5,
                    "points_made": 10,
                },
                "by_bet_family": {"top_name": "dont_pass"},
            }
        ).encode("utf-8")
        z.writestr("artifacts/report.json", payload)

    manifest = {
        "plan": "derived_batch_plan.json",
        "out_dir": str(out_dir),
        "items": [
            {
                "run_id": "RUN1",
                "source": "specs/a.json",
                "input_type": "spec",
                "status": "success",
                "artifacts_dir": str(run1_dir),
                "output_zip": None,
            },
            {
                "run_id": "RUN2",
                "source": "inputs/bundle.zip",
                "input_type": "zip",
                "status": "success",
                "artifacts_dir": None,
                "output_zip": str(out_zip),
            },
        ],
    }
    _write_json(out_dir / "batch_manifest.json", manifest)

    out = aggregate(str(out_dir), leaderboard_metric="ROI", top_k=5, write_comparisons=True)
    assert os.path.isfile(out["leaderboard_path"])
    assert os.path.isfile(out["leaderboard_csv_path"])
    assert os.path.isfile(out["comparisons_path"])

    # Validate leaderboard order: RUN1 ROI=0.2 vs RUN2 ROI=-0.1
    lb = json.loads(Path(out["leaderboard_path"]).read_text("utf-8"))
    assert [r["run_id"] for r in lb][:2] == ["RUN1", "RUN2"]


def test_cli_metric_switch_integration(tmp_path, monkeypatch):
    # Build an out_dir with batch_manifest + reports so aggregator can run
    out_dir = tmp_path / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    r1 = out_dir / "R1"
    r1.mkdir()
    _write_json(
        r1 / "report.json",
        {
            "summary": {
                "bankroll_start": 1000,
                "bankroll_final": 1050,
                "hands_played": 10,
                "rolls": 50,
                "max_drawdown": 30,
            }
        },
    )
    r2 = out_dir / "R2"
    r2.mkdir()
    _write_json(
        r2 / "report.json",
        {
            "summary": {
                "bankroll_start": 1000,
                "bankroll_final": 1300,
                "hands_played": 20,
                "rolls": 100,
                "max_drawdown": 120,
            }
        },
    )

    manifest = {
        "plan": "derived_batch_plan.json",
        "out_dir": str(out_dir),
        "items": [
            {
                "run_id": "R1",
                "source": "a.json",
                "input_type": "spec",
                "status": "success",
                "artifacts_dir": str(r1),
                "output_zip": None,
            },
            {
                "run_id": "R2",
                "source": "b.json",
                "input_type": "spec",
                "status": "success",
                "artifacts_dir": str(r2),
                "output_zip": None,
            },
        ],
    }
    _write_json(out_dir / "batch_manifest.json", manifest)

    # Call aggregator directly with metric switch
    out = aggregate(str(out_dir), leaderboard_metric="bankroll_final", top_k=2, write_comparisons=False)
    lb = json.loads(Path(out["leaderboard_path"]).read_text("utf-8"))
    assert [r["run_id"] for r in lb] == ["R2", "R1"]
