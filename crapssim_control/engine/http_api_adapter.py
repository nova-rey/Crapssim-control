"""HTTP-based engine adapter bridging CSC and the CrapsSim Engine API."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

try:  # Optional dependency; adapter can be constructed without httpx when a client is injected.
    import httpx  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - httpx optional in minimal environments
    httpx = None  # type: ignore[assignment]

from .base import EngineAdapter, EngineStateDict
from .http_api_capabilities import (
    DEFAULT_ENGINE_INFO,
    HttpEngineError,
    coerce_success,
    fetch_capabilities,
    transport_error,
)


class HttpEngineAdapter(EngineAdapter):
    """Adapter that talks to a CrapsSim Engine API instance over HTTP."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        client: Any | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self._client = client
        self._owns_client = False
        self._session_id: Optional[str] = None
        self._seed: Optional[int] = None
        self._last_snapshot: EngineStateDict = {}
        self._engine_info: Dict[str, Any] = dict(DEFAULT_ENGINE_INFO)
        self._engine_info["base_url"] = self.base_url
        self._capabilities: Dict[str, Any] = {}

    # ------------------------------------------------------------------ helpers
    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if httpx is None:  # pragma: no cover - httpx missing in environment
            raise RuntimeError("httpx is required for HttpEngineAdapter when no client is provided")
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds)
        self._owns_client = True
        return self._client

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            try:
                self._client.close()
            except Exception:  # pragma: no cover - defensive cleanup
                pass
        self._client = None
        self._owns_client = False

    def _request_json(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Mapping[str, Any]:
        client = self._ensure_client()
        request_fn = getattr(client, method.lower())
        kwargs: Dict[str, Any] = {}
        if payload is not None:
            kwargs["json"] = payload
        # httpx.Client with base_url accepts relative paths; TestClient also works with relative paths
        url = path if hasattr(client, "base_url") else f"{self.base_url}{path}"
        try:
            response = request_fn(url, timeout=self.timeout_seconds, **kwargs)
        except Exception as exc:  # pragma: no cover - transport failure
            raise transport_error(exc) from exc
        return coerce_success(response)

    def _ensure_capabilities(self) -> None:
        if self._capabilities:
            return
        try:
            client = self._ensure_client()
            url = self.base_url if hasattr(client, "base_url") else self.base_url
            info, caps = fetch_capabilities(url, client, self.timeout_seconds)
        except HttpEngineError:
            # keep defaults but record that API fetch failed
            self._engine_info.setdefault("capabilities_source", "static")
            return
        self._engine_info.update(info)
        self._capabilities = caps

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value))
        except Exception:
            return None

    def _normalize_snapshot(self, payload: Mapping[str, Any] | None) -> EngineStateDict:
        data: Mapping[str, Any]
        if isinstance(payload, Mapping):
            data = payload
        else:
            data = {}
        dice_value = data.get("dice")
        dice: Tuple[int, int] | None = None
        if isinstance(dice_value, (list, tuple)) and len(dice_value) == 2:
            try:
                dice = (int(dice_value[0]), int(dice_value[1]))
            except Exception:
                dice = None
        bankroll = self._coerce_float(data.get("bankroll_after"))
        bets_map: Dict[str, float] = {}
        raw_bets = data.get("bets")
        if isinstance(raw_bets, list):
            for bet in raw_bets:
                if not isinstance(bet, Mapping):
                    continue
                key_parts = [bet.get("type"), bet.get("name"), bet.get("id")]
                key = next((str(v) for v in key_parts if isinstance(v, str) and v), None)
                amount = bet.get("amount")
                amt_val = self._coerce_float(amount)
                if key and amt_val is not None:
                    bets_map[key] = amt_val
        snapshot: EngineStateDict = {
            "session_id": data.get("session_id") or self._session_id,
            "hand_id": data.get("hand_id"),
            "roll_seq": data.get("roll_seq"),
            "dice": dice,
            "puck": data.get("puck"),
            "point": data.get("point"),
            "bankroll": bankroll,
            "bankroll_after": bankroll,
            "bets": bets_map,
            "bets_raw": raw_bets if isinstance(raw_bets, list) else [],
            "events": data.get("events", []),
            "identity": data.get("identity", {}),
            "raw": dict(data),
            "seed": self._seed,
        }
        return snapshot

    # ------------------------------------------------------------------ protocol
    def start_session(self, spec: Dict[str, Any], seed: int | None = None) -> None:
        session_spec = dict(spec or {})
        if seed is not None:
            self._seed = int(seed)
        else:
            seed_from_spec = session_spec.get("seed")
            self._seed = int(seed_from_spec) if isinstance(seed_from_spec, int) else None
        payload: Dict[str, Any] = {"spec": session_spec}
        if self._seed is not None:
            payload["seed"] = self._seed
        data = self._request_json("post", "/session/start", payload)
        session_id = data.get("session_id")
        if not isinstance(session_id, str):
            raise HttpEngineError("engine did not return session_id")
        self._session_id = session_id
        self._engine_info["session_id"] = session_id
        self._ensure_capabilities()
        snapshot_payload = data.get("snapshot")
        self._last_snapshot = self._normalize_snapshot(snapshot_payload)
        self._last_snapshot["session_id"] = session_id

    def step_roll(self, dice: Tuple[int, int] | None = None) -> EngineStateDict:
        if not self._session_id:
            raise RuntimeError("start_session() must be called before step_roll().")
        payload: Dict[str, Any] = {"session_id": self._session_id}
        if dice is not None:
            payload["dice"] = [int(dice[0]), int(dice[1])]
        data = self._request_json("post", "/session/roll", payload)
        snapshot = data.get("snapshot")
        self._last_snapshot = self._normalize_snapshot(snapshot)
        return self._last_snapshot

    def apply_action(self, verb: str, args: Dict[str, Any]) -> EngineStateDict:
        if not self._session_id:
            raise RuntimeError("start_session() must be called before apply_action().")
        payload = {
            "session_id": self._session_id,
            "verb": verb,
            "args": dict(args or {}),
        }
        data = self._request_json("post", "/apply_action", payload)
        effect = data.get("effect_summary")
        effect_summary = dict(effect) if isinstance(effect, Mapping) else {}
        snapshot = data.get("snapshot")
        normalized = self._normalize_snapshot(snapshot)
        self._last_snapshot = normalized
        return {"effect_summary": effect_summary, "snapshot": normalized}

    def snapshot_state(self) -> EngineStateDict:
        if self._last_snapshot:
            return dict(self._last_snapshot)
        return {
            "session_id": self._session_id,
            "bankroll": None,
            "bets": {},
            "events": [],
            "seed": self._seed,
        }

    # ------------------------------------------------------------------ metadata
    def get_engine_info(self) -> Dict[str, Any]:
        info = dict(self._engine_info)
        info.setdefault("engine_type", "http_api")
        info.setdefault("engine_name", "crapssim-api")
        info.setdefault("base_url", self.base_url)
        if self._seed is not None:
            info.setdefault("seed", self._seed)
        return info

    def get_capabilities(self) -> Dict[str, Any]:
        self._ensure_capabilities()
        return dict(self._capabilities)
