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

from crapssim_control.cli import _build_parser


def main(spec_path: str) -> None:
    spec_path_obj = Path(spec_path)
    if not spec_path_obj.exists():
        raise FileNotFoundError(spec_path)
    tracemalloc.start()
    t0 = time.time()
    parser = _build_parser()
    args = parser.parse_args(["run", str(spec_path_obj)])
    run_func = getattr(args, "func", None)
    if callable(run_func):
        run_func(args)
    else:
        raise RuntimeError("CLI parser did not attach run handler")
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
