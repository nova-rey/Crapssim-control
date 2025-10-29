"""In-process Node-RED simulator used by the Phase 6 baseline harness."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import Queue, Empty
from typing import Dict, Iterable, List, Optional, Tuple
from urllib import error as urlerror
from urllib import request as urlrequest


@dataclass
class CommandResult:
    """Record of an issued command for debugging/inspection."""

    action: str
    correlation_id: str
    status: int
    reason: Optional[str] = None


class NodeRedSimulator:
    """Tiny deterministic HTTP simulator for the Phase 6 baseline harness."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 1880,
        command_url: str = "http://127.0.0.1:8089/commands",
        bankroll_threshold: float = 900.0,
        source: str = "node-red-sim",
        timeout: float = 1.0,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.command_url = command_url
        self.bankroll_threshold = float(bankroll_threshold)
        self.source = source
        self.timeout = float(timeout)

        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._run_id: Optional[str] = None
        self._command_counter = 0
        self._batch_counter = 0
        self._results: List[CommandResult] = []
        self._command_tasks: (
            "Queue[Optional[Tuple[float, Tuple[str, Dict[str, object]], Optional[str]]]]"
        ) = Queue()

        self._press_patterns = (
            "mid-stairs",
            "inside-press",
            "iron-cross",
            "ladder",
        )
        self._regress_patterns = (
            "half-press",
            "collect-and-regress",
            "field-reset",
            "ladder-reset",
        )
        self._martingale_steps = (
            {"step_key": "field", "delta": 1, "max_level": 4},
            {"step_key": "come", "delta": 2, "max_level": 3},
            {"step_key": "horn", "delta": 1, "max_level": 5},
            {"step_key": "hardways", "delta": 1, "max_level": 4},
        )

        self._rate_limit_pause = 2.8

    # ------------------------------------------------------------------ server
    def start(self) -> None:
        """Start the webhook listener in a background thread."""

        if self._server is not None:
            return

        server = HTTPServer((self.host, self.port), self._handler_factory())
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            name="node-red-sim",
            daemon=True,
        )
        self._thread.start()
        if self._worker is None:
            self._stop_event.clear()
            self._worker = threading.Thread(
                target=self._command_worker,
                name="node-red-sim-worker",
                daemon=True,
            )
            self._worker.start()

    def stop(self) -> None:
        """Stop the webhook listener and wait for the thread to exit."""

        server = self._server
        thread = self._thread
        worker = self._worker
        self._server = None
        self._thread = None
        self._worker = None

        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass

        if thread is not None:
            thread.join(timeout=2.0)
        self._stop_event.set()
        if worker is not None:
            self._command_tasks.put(None)
            worker.join(timeout=2.0)

    # ---------------------------------------------------------------- handlers
    def _handler_factory(self):
        simulator = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:  # pragma: no cover - silence
                return

            def do_POST(self) -> None:  # pragma: no cover - exercised in harness
                if self.path != "/webhook":
                    self.send_response(404)
                    self.end_headers()
                    return

                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except Exception:
                    payload = {}

                simulator._handle_event(payload if isinstance(payload, dict) else {})

                body = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    # ---------------------------------------------------------------- pipeline
    @property
    def results(self) -> Tuple[CommandResult, ...]:
        with self._lock:
            return tuple(self._results)

    def summary(self) -> Dict[str, object]:
        """Return aggregate counts of attempted/accepted/rejected commands."""

        accepted = 0
        rejected: Dict[str, int] = {}
        total = 0
        for result in self.results:
            total += 1
            if result.status == 202:
                accepted += 1
            elif result.status:
                key = result.reason or str(result.status)
                rejected[key] = rejected.get(key, 0) + 1
        with self._lock:
            run_id = self._run_id
        return {"attempted": total, "accepted": accepted, "rejected": rejected, "run_id": run_id}

    def _command_worker(self) -> None:
        while not self._stop_event.is_set() or not self._command_tasks.empty():
            try:
                item = self._command_tasks.get(timeout=0.1)
            except Empty:
                continue
            if item is None:
                break
            if len(item) == 2:
                delay, command = item
                correlation_override = None
            else:
                delay, command, correlation_override = item
            if delay > 0:
                time.sleep(delay)
            action, args = command
            self._post_single(action, args, correlation_override=correlation_override)
            self._command_tasks.task_done()

    def _handle_event(self, payload: Dict[str, object]) -> None:
        nested = payload.get("payload") if isinstance(payload, dict) else None
        if isinstance(nested, dict):
            merged = dict(nested)
            if "event" not in merged and "event" in payload:
                merged["event"] = payload["event"]
            if "run_id" not in merged and isinstance(payload.get("run_id"), str):
                merged["run_id"] = payload["run_id"]
            payload = merged

        event_name = str(payload.get("event") or payload.get("type") or "")
        if not event_name:
            return

        run_id = payload.get("run_id")
        if isinstance(run_id, str) and run_id:
            with self._lock:
                self._run_id = run_id
        if event_name != "roll.processed":
            return

        bankroll_after = payload.get("bankroll_after")
        try:
            bankroll_val = float(bankroll_after)
        except Exception:
            bankroll_val = None

        if bankroll_val is None or bankroll_val >= self.bankroll_threshold:
            return

        schedule = self._build_command_batch(payload)
        if not schedule:
            return
        self._schedule_commands(schedule)

    def _build_command_batch(
        self, payload: Dict[str, object]
    ) -> List[Tuple[float, Tuple[str, Dict[str, object]], Optional[str]]]:
        with self._lock:
            batch_index = self._batch_counter
            self._batch_counter += 1

        pattern = self._press_patterns[batch_index % len(self._press_patterns)]
        next_pattern = self._regress_patterns[batch_index % len(self._regress_patterns)]
        martingale = self._martingale_steps[batch_index % len(self._martingale_steps)]

        duplicate_args = {"pattern": pattern}
        duplicate = ("press_and_collect", duplicate_args)
        schedule: List[Tuple[float, Tuple[str, Dict[str, object]], Optional[str]]] = []
        schedule.append((0.0, duplicate, None))
        schedule.append((0.1, (duplicate[0], dict(duplicate[1])), "last"))
        schedule.append((0.35, duplicate, None))

        point_on = bool(payload.get("point_on"))
        roll_in_hand = int(payload.get("roll_in_hand", 0) or 0)
        if point_on and roll_in_hand == 1:
            third = ("switch_profile", {"target": "Recovery"})
        else:
            third = ("martingale", dict(martingale))
        schedule.append((0.4, third, None))
        if batch_index == 0:
            schedule.append((0.05, ("regress", {"pattern": next_pattern}), None))
            schedule.append(
                (
                    self._rate_limit_pause + 0.6,
                    ("press_and_collect", {"pattern": next_pattern}),
                    None,
                )
            )
        else:
            schedule.append((self._rate_limit_pause, ("regress", {"pattern": next_pattern}), None))
            schedule.append((0.6, ("press_and_collect", {"pattern": next_pattern}), None))

        return schedule

    def _schedule_commands(
        self, schedule: Iterable[Tuple[float, Tuple[str, Dict[str, object]], Optional[str]]]
    ) -> None:
        for item in schedule:
            if not isinstance(item, tuple):
                continue
            if len(item) == 2:
                delay, command = item
                correlation_override = None
            elif len(item) == 3:
                delay, command, correlation_override = item
            else:
                continue
            if not isinstance(command, tuple) or len(command) != 2:
                continue
            action, args = command
            if not isinstance(args, dict):
                args = {}
            sanitized = (str(action), dict(args))
            try:
                delay_val = float(delay)
            except Exception:
                delay_val = 0.0
            self._command_tasks.put((max(0.0, delay_val), sanitized, correlation_override))

    def _post_single(
        self,
        action: str,
        args: Dict[str, object],
        *,
        correlation_override: Optional[str] = None,
    ) -> None:
        with self._lock:
            run_id = self._run_id
            if not run_id:
                return
            if correlation_override == "last" and self._results:
                correlation_id = self._results[-1].correlation_id
            elif isinstance(correlation_override, str) and correlation_override:
                correlation_id = correlation_override
            else:
                self._command_counter += 1
                correlation_id = f"{self.source}-{self._command_counter:04d}"
            if not correlation_id:
                self._command_counter += 1
                correlation_id = f"{self.source}-{self._command_counter:04d}"
        payload = {
            "run_id": run_id,
            "action": action,
            "args": args,
            "source": self.source,
            "correlation_id": correlation_id,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            self.command_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        status = 0
        reason: Optional[str] = None
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as resp:
                resp.read()
                status = resp.getcode()
        except urlerror.HTTPError as exc:  # pragma: no cover - exercised in harness
            status = exc.code
            try:
                body = exc.read().decode("utf-8")
                decoded = json.loads(body) if body else {}
                reason = str(decoded.get("reason")) if isinstance(decoded, dict) else None
            except Exception:
                reason = None
        except Exception:  # pragma: no cover - network issue
            status = 0

        with self._lock:
            self._results.append(
                CommandResult(
                    action=action,
                    correlation_id=correlation_id,
                    status=status,
                    reason=reason,
                )
            )
