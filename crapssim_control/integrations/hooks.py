from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json


class Outbound:
    def __init__(
        self,
        enabled: bool = False,
        url: str | None = None,
        headers: dict | None = None,
        timeout: float = 2.0,
    ):
        self.enabled = bool(enabled)
        self.url = url
        self.headers = headers or {}
        self.timeout = float(timeout)

    def emit(self, event: str, payload: dict) -> bool:
        if not (self.enabled and self.url):
            return False  # no-op
        try:
            body = json.dumps({"event": event, "payload": payload}).encode("utf-8")
            req = Request(
                self.url,
                data=body,
                headers={"Content-Type": "application/json", **self.headers},
                method="POST",
            )
            with urlopen(req, timeout=self.timeout) as resp:
                return 200 <= getattr(resp, "status", 0) < 300
        except (URLError, HTTPError, TimeoutError, Exception):
            # Never raise; hooks are best-effort.
            return False
