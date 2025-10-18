"""
EvoBridge: placeholder interface for future CrapsSim-Evo integration.
Currently inert — does not modify runtime behavior or communicate externally.
"""

import os
import json
from datetime import datetime


class EvoBridge:
    def __init__(self, enabled: bool = False, log_dir: str = "logs") -> None:
        self.enabled = bool(enabled)
        self.log_dir = log_dir
        if self.enabled:
            os.makedirs(log_dir, exist_ok=True)

    def _log(self, event: str, payload: dict) -> None:
        """Simple file log for visibility; will evolve into real Evo handshake later."""
        if not self.enabled:
            return
        try:
            entry = {
                "ts": datetime.utcnow().isoformat() + "Z",
                "event": event,
                "payload": payload,
            }
            with open(
                os.path.join(self.log_dir, "evo_stub.log"), "a", encoding="utf-8"
            ) as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def announce_run(self, manifest: dict) -> None:
        self._log("announce_run", {"run_id": manifest.get("run_id")})

    def record_result(self, summary: dict) -> None:
        self._log("record_result", {"bankroll_final": summary.get("bankroll_final")})

    def tag_trial(self, manifest: dict, tag: str) -> None:
        self._log(
            "tag_trial",
            {"run_id": manifest.get("run_id"), "trial_tag": tag},
        )
