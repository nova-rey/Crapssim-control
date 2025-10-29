"""
CSC Profiling Tool — Phase 16

Profiles controller runtime for duration and memory churn.
Run:  python -m tools.profile_run <spec_path>
"""

import json
import sys
import time
import tracemalloc
from pathlib import Path

from crapssim_control import controller
from crapssim_control.spec_loader import load_spec_file


def main(spec_path: str) -> None:
    spec_path_obj = Path(spec_path)
    if not spec_path_obj.exists():
        raise FileNotFoundError(spec_path)
    spec, _ = load_spec_file(spec_path_obj)
    try:
        spec["_csc_spec_path"] = str(spec_path_obj)
    except Exception:
        pass
    if not hasattr(controller, "run"):
        raise RuntimeError("controller.run is unavailable in this build")
    tracemalloc.start()
    t0 = time.time()
    controller.run(spec)
    elapsed = time.time() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(
        json.dumps(
            {
                "phase": 16,
                "elapsed_sec": round(elapsed, 3),
                "mem_current_kb": current // 1024,
                "mem_peak_kb": peak // 1024,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m tools.profile_run <spec_path>")
    else:
        main(sys.argv[1])
