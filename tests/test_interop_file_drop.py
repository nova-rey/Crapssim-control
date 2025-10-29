import json
import threading
import time
import zipfile
from pathlib import Path

from crapssim_control import export_bundle
from crapssim_control.interop.config import JobIntakeConfig
from crapssim_control.interop.watcher import run_watcher


def fake_runner(spec, run_root, event_cb, stop_event):
    rr = Path(run_root)
    rr.mkdir(parents=True, exist_ok=True)
    (rr / "journal.csv").write_text("roll,bankroll\n1,1000\n", encoding="utf-8")
    (rr / "manifest.json").write_text(
        json.dumps({"journal_schema_version": "1.1", "summary_schema_version": "1.1"}),
        encoding="utf-8",
    )
    (rr / "report.json").write_text(json.dumps({"top_fitness": 1.0}), encoding="utf-8")
    return str(rr)


def test_file_drop_happy(tmp_path):
    root = tmp_path
    runs = root / "runs/g010"
    runs.mkdir(parents=True)
    rr = root / "runs" / "g010_results" / "seed_0001"
    rr.mkdir(parents=True, exist_ok=True)
    (rr / "journal.csv").write_text("roll,bankroll\n1,1000\n")
    (rr / "manifest.json").write_text(
        json.dumps({"journal_schema_version": "1.1", "summary_schema_version": "1.1"})
    )
    (rr / "report.json").write_text(json.dumps({"top_fitness": 1.0}))
    zpath = export_bundle(rr)
    with zipfile.ZipFile(zpath, "a") as z:
        z.writestr("spec.json", json.dumps({"seed": 1, "run": {}}))

    inc = root / "jobs/incoming"
    done = root / "jobs/done"
    inc.mkdir(parents=True)
    done.mkdir(parents=True)

    import hashlib

    h = hashlib.sha256(zpath.read_bytes()).hexdigest()
    job = {
        "schema_version": "0.1",
        "request_id": "evo-" + h[:12],
        "bundle_id": h,
        "bundle_path": str(zpath.relative_to(root)),
        "generation": "g010",
        "seed": 1,
        "run_flags": {"strict": False, "demo_fallbacks": False},
        "max_rolls": None,
        "webhook_url": None,
    }
    job_file = inc / f"{h}.job.json"
    job_file.write_text(json.dumps(job))

    cfg = JobIntakeConfig(root=root)
    stop = threading.Event()
    t = threading.Thread(target=run_watcher, args=(cfg, fake_runner, stop), daemon=True)
    t.start()

    files = []
    for _ in range(30):
        files = list(done.glob("*.done.json"))
        if files:
            break
        time.sleep(0.2)
    stop.set()
    t.join(timeout=2)

    assert files, "no receipt written"
    receipt = json.loads(files[0].read_text())
    assert receipt["status"] == "ok"
    assert receipt["generation"] == "g010"
