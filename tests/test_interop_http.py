from crapssim_control.interop.config import JobIntakeConfig
from crapssim_control.interop.http_api import JobsHTTP
from crapssim_control.orchestration.control_surface import ControlSurface
from crapssim_control.orchestration.event_bus import EventBus


def test_jobs_http_construct(tmp_path):
    bus = EventBus()

    def fake_runner(spec, run_root, event_cb, stop_event):
        return str(tmp_path)

    surface = ControlSurface(fake_runner, bus)
    cfg = JobIntakeConfig(root=tmp_path)
    JobsHTTP(surface, cfg)
