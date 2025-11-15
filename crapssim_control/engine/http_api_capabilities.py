"""Helpers for CrapsSim HTTP engine capability and error mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

DEFAULT_ENGINE_INFO: Dict[str, Any] = {
    "engine_name": "crapssim-api",
    "engine_type": "http_api",
    "capabilities_source": "static",
}


@dataclass(slots=True)
class HttpEngineError(RuntimeError):
    """Structured error raised by the HTTP engine adapter."""

    message: str
    code: str = "engine_http_error"
    status: Optional[int] = None
    details: Optional[Mapping[str, Any]] = None

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


def _error_from_payload(
    payload: Mapping[str, Any] | None, *, status: Optional[int] = None
) -> HttpEngineError:
    if payload is None:
        return HttpEngineError("engine returned HTTP error", status=status)
    code = str(payload.get("code") or payload.get("error") or "engine_http_error")
    text = payload.get("message") or payload.get("detail") or payload.get("error")
    message = str(text or "engine returned error response")
    return HttpEngineError(message, code=code, status=status, details=payload)


def transport_error(exc: Exception) -> HttpEngineError:
    return HttpEngineError(f"HTTP transport failed: {exc}", code="engine_transport_error")


def parse_response_json(response: Any) -> Tuple[int, Mapping[str, Any]]:
    status = getattr(response, "status_code", None)
    try:
        data = response.json()
    except Exception as exc:  # pragma: no cover - defensive
        body = getattr(response, "text", None)
        raise HttpEngineError(
            "engine returned invalid JSON",
            code="engine_invalid_payload",
            status=status,
            details={"body": body, "error": str(exc)},
        ) from exc
    if not isinstance(data, Mapping):
        raise HttpEngineError(
            "engine returned non-mapping JSON",
            code="engine_invalid_payload",
            status=status,
            details={"payload": data},
        )
    return status or 200, data


def coerce_success(response: Any) -> Mapping[str, Any]:
    status, data = parse_response_json(response)
    if status >= 400:
        raise _error_from_payload(data, status=status)
    return data


def build_engine_info(
    base_url: str,
    payload: Mapping[str, Any] | None,
    *,
    source: str,
) -> Dict[str, Any]:
    info = dict(DEFAULT_ENGINE_INFO)
    info["base_url"] = base_url
    info["capabilities_source"] = source
    if payload:
        engine_api = payload.get("engine_api")
        if isinstance(engine_api, Mapping):
            version = engine_api.get("version")
            if isinstance(version, str):
                info["engine_api_version"] = version
        summary = payload.get("summary")
        if isinstance(summary, Mapping):
            info["capabilities_summary"] = dict(summary)
        caps = payload.get("capabilities")
        if isinstance(caps, Mapping):
            info["capabilities"] = dict(caps)
    return info


def fetch_capabilities(
    base_url: str, client: Any, timeout: float | None = None
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    response = client.get(f"{base_url}/capabilities", timeout=timeout)  # type: ignore[arg-type]
    data = coerce_success(response)
    engine_info = build_engine_info(base_url, data, source="api")
    caps = data.get("capabilities")
    caps_payload = dict(caps) if isinstance(caps, Mapping) else {}
    return engine_info, caps_payload
