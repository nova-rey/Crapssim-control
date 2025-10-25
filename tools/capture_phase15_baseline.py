"""Capture a minimal Phase 15 baseline and tag."""
from __future__ import annotations

import json
import time
from pathlib import Path

from crapssim_control.orchestration.control_surface import ControlSurface
from crapssim_control.orchestration.event_bus import EventBus


def dummy_runner(spec, run_root, event_cb, stop_flag):
    base = Path(run_root or ".") / "baselines" / "phase15" / "artifacts_demo"
    base.mkdir(parents=True, exist_ok=True)
    event_cb({"type": "RUN_STARTED_DEMO"})
    (base / "manifest.json").write_text(json.dumps({"demo": True}), encoding="utf-8")
    time.sleep(0.05)
    return str(base)


def main() -> None:
    bus = EventBus()
    surface = ControlSurface(dummy_runner, bus)
    run_id = surface.launch({"name": "baseline_demo"}, ".")

    deadline = time.time() + 3.0
    while time.time() < deadline:
        status = surface.status(run_id)
        if status.state in {"finished", "error"}:
            break
        time.sleep(0.05)

    base_dir = Path("baselines/phase15")
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "events_sample.json").write_text(
        json.dumps([{"type": "RUN_STARTED_DEMO"}], indent=2),
        encoding="utf-8",
    )
    (base_dir / "TAG").write_text("v0.44.0-phase15-baseline\n", encoding="utf-8")
    print("Baseline captured under baselines/phase15/")


if __name__ == "__main__":
    main()
