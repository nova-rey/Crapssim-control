from typing import Any, Dict, Deque, Tuple
from collections import deque
import threading


class CommandQueue:
    def __init__(self):
        self._q: Deque[Dict[str, Any]] = deque()
        self._seen: set[str] = set()  # correlation_id de-dupe
        self._lock = threading.Lock()

    def enqueue(self, cmd: Dict[str, Any]) -> Tuple[bool, str]:
        # requires keys: run_id, action, args, source, correlation_id
        required = {"run_id", "action", "args", "source", "correlation_id"}
        missing = [k for k in required if k not in cmd]
        if missing:
            return False, f"missing:{','.join(missing)}"
        cid = cmd["correlation_id"]
        with self._lock:
            if cid in self._seen:
                return False, "duplicate_correlation_id"
            self._seen.add(cid)
            self._q.append(cmd)
        return True, "accepted"

    def drain(self) -> list[Dict[str, Any]]:
        with self._lock:
            items = list(self._q)
            self._q.clear()
        return items
