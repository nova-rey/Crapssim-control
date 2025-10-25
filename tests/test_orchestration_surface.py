import json
import time
from pathlib import Path

from crapssim_control.orchestration.control_surface import ControlSurface
from crapssim_control.orchestration.event_bus import EventBus


def fake_runner(spec, run_root, event_cb, stop_flag):
    out = Path(run_root or ".") / ("artifacts_" + (spec.get("name") or "run"))
    out.mkdir(parents=True, exist_ok=True)
    event_cb({"type": "JOURNAL_TICK", "i": 1})
    start = time.time()
    while time.time() - start < 0.2:
        if stop_flag.is_set():
            break
        time.sleep(0.02)
    manifest = {"run_id": spec.get("run_id"), "name": spec.get("name", "demo")}
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return str(out)


def test_surface_start_status_stop(tmp_path):
    bus = EventBus()
    surface = ControlSurface(fake_runner, bus)
    run_id = surface.launch({"name": "t1"}, str(tmp_path))
    status = surface.status(run_id)
    assert status.state in {"running", "stopping", "finished"}

    ok = surface.stop(run_id)
    assert ok in {True, False}

    deadline = time.time() + 3.0
    while time.time() < deadline:
        if surface.status(run_id).state in {"finished", "error"}:
            break
        time.sleep(0.05)

    final = surface.status(run_id)
    assert final.finished_at is not None
    assert final.artifacts_dir
    assert Path(final.artifacts_dir).is_dir()
