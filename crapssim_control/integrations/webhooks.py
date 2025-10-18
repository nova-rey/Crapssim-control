"""
Simple webhook publisher for CSC events.
Non-blocking; failures logged but ignored.
"""
import json
import logging
import random
import threading
import time
from typing import Iterable, Optional, Sequence

try:  # pragma: no cover - exercised via monkeypatch in tests
    import requests  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback path
    from crapssim_control._compat import ensure_requests_module

    requests = ensure_requests_module()

log = logging.getLogger("CSC.Webhooks")
log.addHandler(logging.NullHandler())
log.propagate = False


class WebhookPublisher:
    def __init__(
        self,
        targets: Iterable[str] | None = None,
        enabled: bool = True,
        timeout: float = 2.0,
    ) -> None:
        self.targets: Sequence[str] = list(targets or [])
        self.enabled = bool(enabled)
        self.timeout = float(timeout)

    def emit(self, event: str, payload: dict) -> None:
        if not self.enabled or not self.targets:
            return
        data = json.dumps(payload)
        for url in self.targets:
            threading.Thread(
                target=self._post,
                args=(url, event, data),
                daemon=True,
                name=f"webhook:{event}:{url}",
            ).start()

    def _post(self, url: str, event: str, data: str) -> None:
        headers = {
            "Content-Type": "application/json",
            "X-CSC-Event": event,
            "User-Agent": "CSC-Webhook",
        }
        attempts = 0
        last_error: Optional[Exception] = None
        delays = [0.25, 0.5]
        while attempts <= len(delays):
            try:
                requests.post(url, headers=headers, data=data, timeout=self.timeout)
                return
            except Exception as exc:  # pragma: no cover - log-only branch
                last_error = exc
                if attempts >= len(delays):
                    break
                delay = delays[attempts]
                jitter = random.uniform(0, 0.25)
                time.sleep(delay + jitter)
            finally:
                attempts += 1
        if last_error is not None:  # pragma: no cover - log-only branch
            log.warning("Webhook to %s failed after %d attempts: %s", url, attempts, last_error)
