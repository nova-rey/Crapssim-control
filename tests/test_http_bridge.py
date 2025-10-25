import http.client
import json
import socket
import time
from pathlib import Path
import threading

from crapssim_control.orchestration.control_surface import ControlSurface
from crapssim_control.orchestration.event_bus import EventBus
from crapssim_control.orchestration.http_bridge import serve


def _find_free_port():
    sock = socket.socket()
    sock.bind(("", 0))
    addr = sock.getsockname()
    sock.close()
    return addr[1]


def fake_runner(spec, run_root, event_cb, stop_flag):
    out = Path(run_root or ".") / ("artifacts_" + (spec.get("name") or "run"))
    out.mkdir(parents=True, exist_ok=True)
    event_cb({"type": "RUN_HEARTBEAT", "n": 1})
    time.sleep(0.05)
    return str(out)


def test_http_endpoints(tmp_path):
    bus = EventBus()
    surface = ControlSurface(fake_runner, bus)
    port = _find_free_port()
    server = serve("127.0.0.1", port, surface, bus)

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    conn.request(
        "POST",
        "/run/start",
        body=json.dumps({"spec": {"name": "h1"}, "run_root": str(tmp_path)}),
        headers={"Content-Type": "application/json"},
    )
    response = conn.getresponse()
    payload = json.loads(response.read())
    run_id = payload["run_id"]

    conn.request("GET", f"/status?id={run_id}")
    response = conn.getresponse()
    _ = response.read()

    conn.request(
        "POST",
        "/run/stop",
        body=json.dumps({"run_id": run_id}),
        headers={"Content-Type": "application/json"},
    )
    _ = conn.getresponse().read()
    conn.close()
    server.shutdown()


def test_sse_stream(tmp_path):
    bus = EventBus()
    surface = ControlSurface(lambda spec, root, cb, sf: str(tmp_path), bus)
    port = _find_free_port()
    server = serve("127.0.0.1", port, surface, bus)

    ready = threading.Event()
    header_holder: list[str] = []

    def reader() -> None:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/events")
        ready.set()
        response = conn.getresponse()
        header_holder.append(response.getheader("Content-Type") or "")
        response.close()

    thread = threading.Thread(target=reader)
    thread.start()
    assert ready.wait(timeout=1), "request thread did not start"
    bus.publish({"type": "PING", "foo": "bar"})
    thread.join(timeout=2)
    assert header_holder == ["text/event-stream"]
    server.shutdown()
