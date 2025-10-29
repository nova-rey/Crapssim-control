from __future__ import annotations

import threading
from typing import Any, Dict
from urllib.parse import urlparse

from crapssim_control import import_evo_bundle
from crapssim_control.orchestration.control_surface import ControlSurface

from .config import JobIntakeConfig
from .util import sha256_file


class JobsHTTP:
    """Optional HTTP job queue: POST /runs, GET /runs/{id}."""

    def __init__(self, surface: ControlSurface, cfg: JobIntakeConfig, *, max_inflight: int | None = None):
        self.surface = surface
        self.cfg = cfg
        self.max_inflight = max_inflight or cfg.max_inflight
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def post_runs(self, handler, body: Dict[str, Any]) -> None:
        rid = handler.headers.get("Idempotency-Key") or body.get("request_id")
        if not rid:
            handler._json(400, {"error": "missing idempotency key"})
            return
        with self._lock:
            if rid in self._runs:
                handler._json(409, {"run_id": self._runs[rid]["run_id"], "accepted": True})
                return

        try:
            bundle_url = body.get("bundle_url")
            bundle_id = body.get("bundle_id")
            generation = body.get("generation", "")
            seed = int(body.get("seed"))
            flags = body.get("run_flags", {})
            max_rolls = body.get("max_rolls")

            bp = urlparse(bundle_url)
            if bp.scheme != "file":
                handler._json(422, {"error": "only file:// supported in v1"})
                return
            path = bp.path
            calc = sha256_file(path)
            if str(calc) != str(bundle_id):
                handler._json(
                    422,
                    {"error": "BUNDLE_HASH_MISMATCH", "detail": f"expected {bundle_id}, got {calc}"},
                )
                return

            spec, meta = import_evo_bundle(path)
            spec.setdefault("seed", seed)
            spec.setdefault("run", {})
            spec["run"]["strict"] = bool(flags.get("strict", self.cfg.strict_default))
            spec["run"]["demo_fallbacks"] = bool(flags.get("demo_fallbacks", self.cfg.demo_fallbacks_default))
            if max_rolls is not None:
                spec["run"]["max_rolls"] = int(max_rolls)

            gen_root = self.cfg.root / f"{self.cfg.results_root}/{generation}_results"
            seed_dir = gen_root / f"seed_{seed:04d}"
            seed_dir.mkdir(parents=True, exist_ok=True)

            run_id = self.surface.launch(spec, str(seed_dir))
            with self._lock:
                self._runs[rid] = {"run_id": run_id}
            handler._json(202, {"run_id": run_id, "accepted": True})
        except Exception as e:  # pragma: no cover - HTTP integration handles logging
            handler._json(422, {"error": "VALIDATION_ERROR", "detail": str(e)})

    def get_run(self, handler, run_id: str) -> None:
        st = self.surface.status(run_id)
        payload = {
            "run_id": run_id,
            "status": st.state,
            "results_root": st.artifacts_dir if st.artifacts_dir else None,
            "error_code": None if st.error is None else "ENGINE_FAIL",
            "error_detail": st.error,
        }
        handler._json(200, payload)
