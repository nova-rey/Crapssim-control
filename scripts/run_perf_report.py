"""Generate a lightweight performance report for Phase 9."""

from __future__ import annotations

import datetime
import json
import pathlib

from crapssim_control.replay_tester import run_perf_test


def main() -> None:
    res = run_perf_test()
    out = {
        "timestamp": datetime.datetime.utcnow().isoformat(timespec="seconds"),
        "rolls": res["rolls"],
        "elapsed": round(res["elapsed"], 3),
        "rps": int(res["rps"]),
    }
    out_path = pathlib.Path("reports") / "phase9_perf.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("## Phase 9 Performance Report\n\n```\n")
        f.write(json.dumps(out, indent=2))
        f.write("\n```")
    print(out)


if __name__ == "__main__":
    main()
