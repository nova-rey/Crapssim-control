from typing import Any, Dict, Deque, Tuple, Iterable, Optional, Callable, List
from collections import defaultdict, deque
import threading
import logging
import time


logger = logging.getLogger(__name__)


DEFAULT_LIMITS = {
    "queue_max_depth": 100,
    "per_source_quota": 40,
    "rate": {"tokens": 3, "refill_seconds": 2.0},
    "circuit_breaker": {"consecutive_rejects": 10, "cool_down_seconds": 10.0},
}


class RateLimiter:
    def __init__(self, tokens: int, refill_seconds: float) -> None:
        self.tokens = max(1, int(tokens))
        self.refill_seconds = float(refill_seconds)
        self._available = self.tokens
        self._last_refill = time.time()

    def allow(self) -> bool:
        now = time.time()
        if now - self._last_refill >= self.refill_seconds:
            refill = int((now - self._last_refill) / self.refill_seconds)
            if refill > 0:
                self._available = min(self.tokens, self._available + refill)
                self._last_refill = now
        if self._available > 0:
            self._available -= 1
            return True
        return False


class CircuitBreaker:
    def __init__(self, max_rejects: int, cool_down: float) -> None:
        self.max_rejects = max(1, int(max_rejects))
        self.cool_down = float(cool_down)
        self.consecutive = 0
        self.tripped_until = 0.0

    def record(self, success: bool) -> Optional[str]:
        if success:
            if self.consecutive >= self.max_rejects:
                self.consecutive = 0
                return "reset"
            self.consecutive = 0
        else:
            self.consecutive += 1
            if self.consecutive >= self.max_rejects:
                self.tripped_until = time.time() + self.cool_down
                return "trip"
        return None

    def allow(self) -> bool:
        return time.time() >= self.tripped_until

REQUIRED_KEYS = {"run_id", "action", "args", "source", "correlation_id"}
ALLOWED_ACTIONS = {"switch_profile", "regress", "press_and_collect", "martingale"}


class CommandQueue:
    def __init__(self, limits: Optional[Dict[str, Any]] = None):
        self.limits = self._merge_limits(limits)
        self._q: Deque[Dict[str, Any]] = deque()
        self._seen: set[str] = set()
        self._lock = threading.Lock()
        self._per_source_counts: Dict[str, int] = defaultdict(int)
        self._rate_limiters: Dict[str, RateLimiter] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.stats = {
            "enqueued": 0,
            "executed": 0,
            "rejected": defaultdict(int),
        }
        self._rejection_handlers: List[Callable[[Dict[str, Any]], None]] = []

    @staticmethod
    def _merge_limits(limits: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        def _to_dict(val: Any) -> Any:
            if isinstance(val, dict):
                return {k: _to_dict(v) for k, v in val.items()}
            if hasattr(val, "__dict__"):
                return {k: _to_dict(v) for k, v in vars(val).items()}
            return val

        result = {k: _to_dict(v) for k, v in DEFAULT_LIMITS.items()}
        if limits is None:
            return result
        raw = _to_dict(limits)
        if not isinstance(raw, dict):
            return result
        for key, value in raw.items():
            if key not in result:
                result[key] = value
                continue
            if isinstance(result[key], dict) and isinstance(value, dict):
                merged = dict(result[key])
                merged.update({k: _to_dict(v) for k, v in value.items()})
                result[key] = merged
            else:
                result[key] = value
        return result

    def _get_limiter(self, source: str) -> RateLimiter:
        limiter = self._rate_limiters.get(source)
        if limiter is None:
            rate_cfg = self.limits.get("rate", {}) or {}
            tokens = rate_cfg.get("tokens", DEFAULT_LIMITS["rate"]["tokens"])
            refill_seconds = rate_cfg.get(
                "refill_seconds",
                DEFAULT_LIMITS["rate"]["refill_seconds"],
            )
            limiter = RateLimiter(tokens, refill_seconds)
            self._rate_limiters[source] = limiter
        return limiter

    def _get_breaker(self, source: str) -> CircuitBreaker:
        breaker = self._circuit_breakers.get(source)
        if breaker is None:
            cb_cfg = self.limits.get("circuit_breaker", {}) or {}
            max_rejects = cb_cfg.get(
                "consecutive_rejects",
                DEFAULT_LIMITS["circuit_breaker"]["consecutive_rejects"],
            )
            cool_down = cb_cfg.get(
                "cool_down_seconds",
                DEFAULT_LIMITS["circuit_breaker"]["cool_down_seconds"],
            )
            breaker = CircuitBreaker(max_rejects, cool_down)
            self._circuit_breakers[source] = breaker
        return breaker

    def add_rejection_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        if handler not in self._rejection_handlers:
            self._rejection_handlers.append(handler)

    def _reject_locked(
        self,
        source: str,
        reason: str,
        *,
        update_breaker: bool = True,
        cmd: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        if update_breaker:
            breaker = self._get_breaker(source)
            event = breaker.record(False)
            if event == "trip":
                logger.warning("Command source '%s' tripped circuit breaker", source)
        self.stats["rejected"][reason] += 1
        payload = {
            "source": source,
            "reason": reason,
            "command": cmd,
        }
        for handler in list(self._rejection_handlers):
            try:
                handler(payload)
            except Exception:
                logger.exception("Command rejection handler failed")
        return False, reason

    def enqueue(self, cmd: Dict[str, Any]) -> Tuple[bool, str]:
        with self._lock:
            source_label = str(cmd.get("source", "external"))
            cid = str(cmd.get("correlation_id", "")).strip()
            if not cid:
                return self._reject_locked(source_label, "missing:correlation_id", cmd=cmd)

            missing = [k for k in REQUIRED_KEYS if k not in cmd]
            if missing:
                missing_key = str(sorted(missing)[0])
                return self._reject_locked(source_label, f"missing:{missing_key}", cmd=cmd)

            action = cmd.get("action")
            if action not in ALLOWED_ACTIONS:
                return self._reject_locked(source_label, "unknown_action", cmd=cmd)

            if cid in self._seen:
                return self._reject_locked(source_label, "timing:duplicate_correlation_id", cmd=cmd)

            replay_mode = bool(cmd.pop("_csc_replay", False))

            if not replay_mode:
                queue_max = int(
                    self.limits.get("queue_max_depth", DEFAULT_LIMITS["queue_max_depth"])
                )
                if len(self._q) >= queue_max:
                    return self._reject_locked(source_label, "queue_full", cmd=cmd)

                per_source_max = int(
                    self.limits.get("per_source_quota", DEFAULT_LIMITS["per_source_quota"])
                )
                if self._per_source_counts[source_label] >= per_source_max:
                    return self._reject_locked(source_label, "per_source_quota", cmd=cmd)

                limiter = self._get_limiter(source_label)
                if not limiter.allow():
                    return self._reject_locked(source_label, "rate_limited", cmd=cmd)

                breaker = self._get_breaker(source_label)
                if not breaker.allow():
                    return self._reject_locked(
                        source_label,
                        "circuit_breaker",
                        update_breaker=False,
                        cmd=cmd,
                    )
            else:
                # Replay injections bypass runtime rate/circuit enforcement but still
                # participate in duplicate detection and queue stats.
                breaker = self._get_breaker(source_label)

            payload = {
                "run_id": str(cmd["run_id"]),
                "action": str(action),
                "args": cmd.get("args", {}) or {},
                "source": source_label,
                "correlation_id": cid,
            }
            self._seen.add(cid)
            self._q.append(payload)
            self._per_source_counts[source_label] += 1
            self.stats["enqueued"] += 1
            return True, "accepted"

    def drain(self) -> Iterable[Dict[str, Any]]:
        with self._lock:
            items = list(self._q)
            self._q.clear()
            self._per_source_counts = defaultdict(int)
        return items

    def record_outcome(
        self,
        source: str,
        *,
        executed: bool,
        rejection_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        reset = False
        with self._lock:
            breaker = self._get_breaker(source)
            if executed:
                event = breaker.record(True)
                if event == "reset":
                    reset = True
                self.stats["executed"] += 1
            else:
                event = breaker.record(False)
                if event == "trip":
                    logger.warning(
                        "Command source '%s' tripped circuit breaker", source
                    )
                if rejection_reason:
                    self.stats["rejected"][rejection_reason] += 1
        return {"circuit_breaker_reset": reset}
