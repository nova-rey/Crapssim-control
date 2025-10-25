from __future__ import annotations

import json
import threading
from collections import deque
from queue import Queue
from typing import Any, Deque, Dict, Iterable, Tuple

Event = Dict[str, Any]


class EventBus:
    """Simple in-process pub/sub bus for orchestration events."""

    def __init__(self) -> None:
        self._subs: Dict[int, Queue] = {}
        self._lock = threading.Lock()
        self._next_id = 1
        # Retain a bounded backlog so new subscribers do not miss events that
        # were published in the window before their registration completes.
        self._history: Deque[Event] = deque(maxlen=1000)

    def subscribe(self) -> Tuple[int, Queue]:
        """Register a new subscriber and return its id and queue."""

        with self._lock:
            sid = self._next_id
            self._next_id += 1
            queue: Queue = Queue(maxsize=1000)
            self._subs[sid] = queue
            backlog: Iterable[Event] = tuple(self._history)

        for event in backlog:
            try:
                queue.put_nowait(event)
            except Exception:
                # If the queue fills from the backlog, drop the oldest items.
                break

        return sid, queue

    def unsubscribe(self, sid: int) -> None:
        with self._lock:
            self._subs.pop(sid, None)

    def publish(self, event: Event) -> None:
        with self._lock:
            self._history.append(event)
            queues = tuple(self._subs.values())

        for queue in queues:
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
