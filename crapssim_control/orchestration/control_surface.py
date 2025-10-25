from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from ..plugins.loader import PluginLoader
from ..plugins.registry import PluginRegistry
from ..plugins.runtime import (
    clear_registries,
    default_sandbox_policy,
    load_plugins_for_spec,
    write_plugins_manifest,
)
from .event_bus import EventBus


@dataclass
class RunStatus:
    run_id: str
    state: str = "idle"
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    artifacts_dir: Optional[str] = None
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class ControlSurface:
    """Thin orchestration wrapper that manages run lifecycle."""

    def __init__(self, runner: Callable[..., str], bus: EventBus) -> None:
        self._runner = runner
        self._bus = bus
        self._runs: Dict[str, RunStatus] = {}
        self._stop_flags: Dict[str, threading.Event] = {}

    def launch(self, spec: Dict[str, Any], run_root: str) -> str:
        run_id = spec.get("run_id") or uuid.uuid4().hex[:12]
        status = RunStatus(run_id=run_id, state="running", started_at=time.time())
        self._runs[run_id] = status
        self._stop_flags[run_id] = threading.Event()

        self._bus.publish(
            {
                "type": "RUN_STARTED",
                "run_id": run_id,
                "ts": time.time(),
                "spec_hint": spec.get("name"),
            }
        )

        plugins_loaded = []
        try:
            registry = PluginRegistry()
            candidate_roots = []
            if run_root and os.path.isdir(os.path.join(run_root, "plugins")):
                candidate_roots.append(os.path.join(run_root, "plugins"))
            if os.path.isdir("plugins"):
                candidate_roots.append("plugins")
            registry.discover(candidate_roots)
            loader = PluginLoader(default_sandbox_policy())
            plugins_loaded = load_plugins_for_spec(spec, registry, loader)
        except Exception as exc:  # pragma: no cover - defensive
            plugins_loaded = [{"status": "error", "detail": f"plugin_load_failed:{exc}"}]

        def event_cb(event: Dict[str, Any]) -> None:
            event["run_id"] = run_id
            event["ts"] = time.time()
            self._bus.publish(event)

        def run_thread() -> None:
            try:
                artifacts_dir = self._runner(spec, run_root, event_cb, self._stop_flags[run_id])
                status.artifacts_dir = artifacts_dir
                if artifacts_dir:
                    try:
                        write_plugins_manifest(artifacts_dir, plugins_loaded)
                    except Exception:  # pragma: no cover - best effort
                        pass
                status.state = "finished"
            except Exception as exc:  # pragma: no cover - runner failure
                status.error = str(exc)
                status.state = "error"
            finally:
                status.finished_at = time.time()
                clear_registries()
                self._bus.publish(
                    {
                        "type": "RUN_FINISHED",
                        "run_id": run_id,
                        "ts": time.time(),
                        "state": status.state,
                        "error": status.error,
                    }
                )

        thread = threading.Thread(target=run_thread, daemon=True)
        thread.start()
        return run_id

    def status(self, run_id: str) -> RunStatus:
        if run_id not in self._runs:
            raise KeyError(f"Unknown run_id {run_id}")
        return self._runs[run_id]

    def stop(self, run_id: str) -> bool:
        flag = self._stop_flags.get(run_id)
        status = self._runs.get(run_id)
        if flag and status and status.state == "running":
            status.state = "stopping"
            flag.set()
            self._bus.publish({"type": "RUN_STOP_SIGNAL", "run_id": run_id, "ts": time.time()})
            return True
        return False
