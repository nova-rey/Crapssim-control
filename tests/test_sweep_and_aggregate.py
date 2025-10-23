import json
import os
from pathlib import Path
from typing import Any, Dict
import zipfile

import pytest

from crapssim_control.sweep import expand_plan, run_sweep
from crapssim_control.aggregator import aggregate


# --- helpers ---------------------------------------------------------

def _write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def _mk_template_spec(tmp_path, bankroll=1000, table_min=5, profile="demo"):
    tp = tmp_path / "template.json"
    _write_json(tp, {"name": "tmpl", "bankroll": bankroll, "table_min": table_min, "profile": profile})
    return str(tp)


def _mk_sweep_grid(tmp_path, template_path):
    plan = {
        "mode": "grid",
        "out_dir": str(tmp_path / "exports"),
        "template": template_path,
        "vars": {
            "bankroll": [500, 1000, 2000],
            "table_min": [5, 10],
        },
        "max_items": 50,
    }
    pp = tmp_path / "sweep_grid.yaml"
    _write_json(pp, plan)
    return str(pp)


def _mk_sweep_explicit(tmp_path, items):
    plan = {
        "mode": "explicit",
        "out_dir": str(tmp_path / "exports"),
        "items": [{"path": it} for it in items],
    }
    pp = tmp_path / "sweep_explicit.json"
    _write_json(pp, plan)
    return str(pp)


def _mk_zip_with_report(tmp_path) -> str:
    # create an input zip with spec + dna + meta
    bdir = tmp_path / "bundle"
    (bdir / "dna").mkdir(parents=True, exist_ok=True)
    (bdir / "meta").mkdir(parents=True, exist_ok=True)
    _write_json(bdir / "spec.json", {"name": "zipdemo", "bankroll": 777})
    with open(bdir / "dna" / "notes.txt", "wb") as f:
        f.write(b"hello-dna")
    with open(bdir / "meta" / "marker.bin", "wb") as f:
        f.write(b"\x00\x01\x02")

    zp = tmp_path / "input.zip"
    with zipfile.ZipFile(zp, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(bdir):
            for fn in files:
                ap = Path(root) / fn
                rel = str(ap.relative_to(bdir)).replace("\\", "/")
                z.write(str(ap), arcname=rel)
    return str(zp)


# --- tests -----------------------------------------------------------


def test_grid_expansion_counts(tmp_path):
    template = _mk_template_spec(tmp_path)
    plan = _mk_sweep_grid(tmp_path, template)
    items, out_dir, _ = expand_plan(plan)
    assert out_dir.endswith("exports")
    assert len(items) == 3 * 2  # 3 bankrolls × 2 table_min


def test_aggregator_handles_success_and_error(tmp_path, monkeypatch):
    # We'll fabricate a batch_manifest.json and reports for 2 runs
    out_dir = tmp_path / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Success record with artifacts_dir report
    run_a_dir = out_dir / "AAA"
    run_a_dir.mkdir()
    _write_json(run_a_dir / "report.json", {
        "summary": {
            "bankroll_start": 1000, "bankroll_final": 1100,
            "hands_played": 50, "rolls": 250, "max_drawdown": 80,
            "pso_count": 3, "points_made": 12
        },
        "by_bet_family": {"top_name": "place_6_8"}
    })

    # Error record (no report)
    batch_manifest = {
        "plan": "derived_batch_plan.json",
        "out_dir": str(out_dir),
        "items": [
            {"run_id": "AAA", "source": "specs/a.json", "input_type": "spec", "status": "success", "artifacts_dir": str(run_a_dir), "output_zip": None},
            {"run_id": "BBB", "source": "specs/b.json", "input_type": "spec", "status": "error", "error": "boom"}
        ],
    }
    _write_json(out_dir / "batch_manifest.json", batch_manifest)

    out = aggregate(str(out_dir), top_k=5)
    assert os.path.isfile(out["index_path"])
    assert os.path.isfile(out["csv_path"])
    assert os.path.isfile(out["aggregates_path"])
    assert os.path.isfile(out["leaderboard_path"])

    # Load index and check fields
    index = json.loads(Path(out["index_path"]).read_text("utf-8"))
    assert len(index) == 2
    a = next(r for r in index if r["run_id"] == "AAA")
    assert a["ROI"] == 0.1
    b = next(r for r in index if r["run_id"] == "BBB")
    assert b["error"] == "boom"


def test_sweep_runs_and_index_with_mock_batch(tmp_path, monkeypatch):
    """
    Mock run_batch to avoid invoking real engine. Verify that run_sweep writes derived plan and aggregator produces outputs.
    """
    # Prepare explicit plan with one spec and one zip
    spec = tmp_path / "spec.json"
    _write_json(spec, {"name": "demo", "bankroll": 1000})
    zip_in = _mk_zip_with_report(tmp_path)
    plan_path = Path(_mk_sweep_explicit(tmp_path, [str(spec), zip_in]))

    out_dir = tmp_path / "exports"

    # Mock batch_runner.run_batch to write a batch_manifest and a fake output zip with report.json inside artifacts/
    def fake_run_batch(derived_plan_path: str):
        # create artifacts for first item (spec) as a directory
        run1 = out_dir / "RUN1"
        run1.mkdir(parents=True, exist_ok=True)
        _write_json(run1 / "report.json", {
            "summary": {"bankroll_start": 1000, "bankroll_final": 1200, "hands_played": 60, "rolls": 300, "max_drawdown": 90, "pso_count": 2, "points_made": 15},
            "by_bet_family": {"top_name": "pass_line"}
        })
        # create an output zip for second item with artifacts/report.json
        out_zip = out_dir / "RUN2.zip"
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            payload = json.dumps({
                "summary": {"bankroll_start": 1000, "bankroll_final": 900, "hands_played": 55, "rolls": 280, "max_drawdown": 150, "pso_count": 5, "points_made": 10},
                "by_bet_family": {"top_name": "dont_pass"}
            }).encode("utf-8")
            z.writestr("artifacts/report.json", payload)

        manifest = {
            "plan": os.path.basename(derived_plan_path),
            "out_dir": str(out_dir),
            "items": [
                {"run_id": "RUN1", "source": str(spec), "input_type": "spec", "status": "success", "artifacts_dir": str(run1), "output_zip": None},
                {"run_id": "RUN2", "source": zip_in, "input_type": "zip", "status": "success", "artifacts_dir": None, "output_zip": str(out_zip)},
            ],
        }
        _write_json(out_dir / "batch_manifest.json", manifest)
        return manifest

    from crapssim_control import batch_runner as br
    monkeypatch.setattr(br, "run_batch", fake_run_batch)

    # Execute sweep (will call our mock)
    manifest_path = run_sweep(str(plan_path))
    assert os.path.isfile(manifest_path)

    # Aggregate
    out = aggregate(str(out_dir), top_k=5)
    index = json.loads(Path(out["index_path"]).read_text("utf-8"))
    assert len(index) == 2
    r1 = next(r for r in index if r["run_id"] == "RUN1")
    r2 = next(r for r in index if r["run_id"] == "RUN2")
    assert r1["ROI"] == 0.2
    assert r2["ROI"] == -0.1
