from typing import Any, Dict, Deque, Tuple, Iterable
from collections import deque
import threading

REQUIRED_KEYS = {"run_id", "action", "args", "source", "correlation_id"}
ALLOWED_ACTIONS = {"switch_profile", "regress", "press_and_collect", "martingale"}


class CommandQueue:
    def __init__(self):
        self._q: Deque[Dict[str, Any]] = deque()
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def enqueue(self, cmd: Dict[str, Any]) -> Tuple[bool, str]:
        # coerce correlation id to string to normalize dedupe
        cid = str(cmd.get("correlation_id", "")).strip()
        if not cid:
            return False, "missing:correlation_id"
        missing = [k for k in REQUIRED_KEYS if k not in cmd]
        if missing:
            return False, f"missing:{','.join(sorted(missing))}"
        if cmd.get("action") not in ALLOWED_ACTIONS:
            return False, "unknown_action"
        with self._lock:
            if cid in self._seen:
                return False, "duplicate_correlation_id"
            self._seen.add(cid)
            self._q.append({
                "run_id": str(cmd["run_id"]),
                "action": str(cmd["action"]),
                "args": cmd.get("args", {}),
                "source": str(cmd.get("source", "external")),
                "correlation_id": cid,
            })
        return True, "accepted"

    def drain(self) -> Iterable[Dict[str, Any]]:
        with self._lock:
            items = list(self._q)
            self._q.clear()
        return items
