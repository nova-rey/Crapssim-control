from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict

from crapssim_control import export_bundle, import_evo_bundle
from crapssim_control.orchestration.control_surface import ControlSurface
from crapssim_control.orchestration.event_bus import EventBus

from .config import JobIntakeConfig
from .jobs import DoneReceipt, ErrorReceipt, EvoJob
from .util import read_json, sha256_file, write_json


class _Seen:
    def __init__(self) -> None:
        self._s: set[str] = set()
        self._lock = threading.Lock()

    def check_and_mark(self, key: str) -> bool:
        with self._lock:
            if key in self._s:
                return True
            self._s.add(key)
            return False


def _job_from_json(d: Dict[str, Any]) -> EvoJob:
    return EvoJob(
        schema_version=d.get("schema_version", ""),
        request_id=d["request_id"],
        bundle_id=d["bundle_id"],
        bundle_path=d["bundle_path"],
        generation=d["generation"],
        seed=int(d["seed"]),
        run_flags=d.get("run_flags", {}),
        max_rolls=d.get("max_rolls"),
        webhook_url=d.get("webhook_url"),
    )


def run_watcher(
    cfg: JobIntakeConfig,
    runner: Callable[[Dict[str, Any], str, Callable[[Dict[str, Any]], None], threading.Event], str],
    stop_flag: threading.Event | None = None,
) -> None:
    """Poll jobs/incoming/*.job.json and process per Evo brief."""

    seen = _Seen()
    bus = EventBus()
    surface = ControlSurface(runner, bus)
    stop = stop_flag or threading.Event()

    while not stop.is_set():
        incoming = sorted(p for p in cfg.incoming_dir.glob("*.job.json") if p.is_file())
        inflight = 0
        for job_file in incoming:
            if inflight >= cfg.max_inflight:
                break

            payload = read_json(job_file)
            job = _job_from_json(payload)

            if seen.check_and_mark(job.request_id):
                continue

            bundle_abs = (cfg.root / job.bundle_path).resolve()
            calc = sha256_file(bundle_abs)
            if calc != job.bundle_id:
                err = ErrorReceipt(
                    request_id=job.request_id,
                    bundle_id=job.bundle_id,
                    generation=job.generation,
                    error_code="BUNDLE_HASH_MISMATCH",
                    error_detail=f"expected {job.bundle_id}, got {calc}",
                )
                write_json(cfg.done_dir / f"{job.request_id}.done.json", err.__dict__)
                job_file.unlink(missing_ok=True)
                continue

            try:
                spec, meta = import_evo_bundle(bundle_abs)
                spec.setdefault("seed", job.seed)
                spec.setdefault("run", {})
                spec["run"].setdefault("strict", cfg.strict_default)
                spec["run"]["strict"] = bool(job.run_flags.get("strict", cfg.strict_default))
                spec["run"].setdefault("demo_fallbacks", cfg.demo_fallbacks_default)
                spec["run"]["demo_fallbacks"] = bool(
                    job.run_flags.get("demo_fallbacks", cfg.demo_fallbacks_default)
                )
                if job.max_rolls is not None:
                    spec["run"]["max_rolls"] = int(job.max_rolls)

                gen_root = cfg.root / f"{cfg.results_root}/{job.generation}_results"
                seed_dir = gen_root / f"seed_{job.seed:04d}"
                seed_dir.mkdir(parents=True, exist_ok=True)

                run_id = surface.launch(spec, str(seed_dir))
                st = surface.status(run_id)
                while st.state not in ("finished", "error"):
                    time.sleep(0.5)
                    st = surface.status(run_id)

                try:
                    export_bundle(st.artifacts_dir)
                except Exception:
                    pass

                summary_path = Path(st.artifacts_dir) / "report.json"
                summary: Dict[str, Any] = {}
                try:
                    summary = read_json(summary_path)
                except Exception:
                    pass

                done = DoneReceipt(
                    request_id=job.request_id,
                    bundle_id=job.bundle_id,
                    generation=job.generation,
                    run_id=run_id,
                    results_root=str(gen_root),
                    summary={
                        "top_fitness": summary.get("top_fitness"),
                        "elapsed_s": summary.get("elapsed_s"),
                        "pop_size": summary.get("pop_size"),
                    },
                )
                write_json(cfg.done_dir / f"{job.request_id}.done.json", done.__dict__)
            except Exception as e:  # pragma: no cover - best effort error path
                err = ErrorReceipt(
                    request_id=job.request_id,
                    bundle_id=job.bundle_id,
                    generation=job.generation,
                    run_id=f"error-{int(time.time())}",
                    error_code="ENGINE_FAIL",
                    error_detail=str(e),
                    partial_results_root=str(cfg.root / f"{cfg.results_root}/{job.generation}_results"),
                )
                write_json(cfg.done_dir / f"{job.request_id}.done.json", err.__dict__)
            finally:
                job_file.unlink(missing_ok=True)

            inflight += 1
        time.sleep(1.0)
