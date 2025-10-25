from __future__ import annotations

import json
import threading
from queue import Queue
from typing import Any, Dict, Tuple

Event = Dict[str, Any]


class EventBus:
    """Simple in-process pub/sub bus for orchestration events."""

    def __init__(self) -> None:
        self._subs: Dict[int, Queue] = {}
        self._lock = threading.Lock()
        self._next_id = 1

    def subscribe(self) -> Tuple[int, Queue]:
        """Register a new subscriber and return its id and queue."""

        with self._lock:
            sid = self._next_id
            self._next_id += 1
            queue: Queue = Queue(maxsize=1000)
            self._subs[sid] = queue
        return sid, queue

    def unsubscribe(self, sid: int) -> None:
        with self._lock:
            self._subs.pop(sid, None)

    def publish(self, event: Event) -> None:
        with self._lock:
            for queue in self._subs.values():
                try:
                    queue.put_nowait(event)
                except Exception:
                    # Best-effort delivery for live feeds. Drop on overflow.
                    pass

    @staticmethod
    def to_sse(event: Event) -> bytes:
        """Encode an event as SSE bytes."""

        payload = json.dumps(event, separators=(",", ":"))
        return f"data: {payload}\n\n".encode("utf-8")
