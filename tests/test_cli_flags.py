from argparse import Namespace
from copy import deepcopy

from crapssim_control import cli
from crapssim_control.config import (
    DEMO_FALLBACKS_DEFAULT,
    EMBED_ANALYTICS_DEFAULT,
    STRICT_DEFAULT,
)
from crapssim_control.controller import ControlStrategy


def _spec(run: dict | None = None) -> dict:
    spec = {
        "table": {},
        "variables": {"units": 10},
        "modes": {"Main": {"template": {}}},
        "rules": [],
    }
    if run is not None:
        spec["run"] = run
    return spec


def _args(**kwargs) -> Namespace:
    defaults = {
        "demo_fallbacks": False,
        "strict": False,
        "no_embed_analytics": False,
    }
    defaults.update(kwargs)
    return Namespace(**defaults)


def test_cli_flags_default_no_override():
    spec = _spec()
    before = deepcopy(spec)
    cli._merge_cli_run_flags(spec, _args())
    assert spec == before
    assert "run" not in spec


def test_cli_flags_override_spec_run_values():
    spec = _spec({"rolls": 42, "csv": {"embed_analytics": True}})
    cli._merge_cli_run_flags(
        spec,
        _args(demo_fallbacks=True, strict=True, no_embed_analytics=True),
    )
    run = spec["run"]
    assert run.get("rolls") == 42
    assert run.get("demo_fallbacks") is True
    assert run.get("strict") is True
    assert run.get("csv", {}).get("embed_analytics") is False


def test_report_metadata_reflects_cli_flags():
    spec = _spec()
    cli._merge_cli_run_flags(
        spec,
        _args(demo_fallbacks=True, strict=True, no_embed_analytics=True),
    )
    ctrl = ControlStrategy(spec)
    report = ctrl.generate_report()
    flags = report.get("metadata", {}).get("run_flags")
    assert flags == {
        "demo_fallbacks": True,
        "strict": True,
        "embed_analytics": False,
    }

    # Without CLI overrides the defaults should remain intact
    base = ControlStrategy(_spec())
    base_report = base.generate_report()
    base_flags = base_report.get("metadata", {}).get("run_flags")
    assert base_flags == {
        "demo_fallbacks": DEMO_FALLBACKS_DEFAULT,
        "strict": STRICT_DEFAULT,
        "embed_analytics": EMBED_ANALYTICS_DEFAULT,
    }
