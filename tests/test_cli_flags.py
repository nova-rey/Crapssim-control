import argparse
from argparse import Namespace
from copy import deepcopy

from crapssim_control import cli
from crapssim_control.config import (
    DEMO_FALLBACKS_DEFAULT,
    EMBED_ANALYTICS_DEFAULT,
    STRICT_DEFAULT,
)
from crapssim_control.spec_validation import VALIDATION_ENGINE_VERSION
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
        "webhook_url": None,
        "webhook_timeout": None,
        "no_webhook": False,
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
    metadata = report.get("metadata", {})
    flags = metadata.get("run_flags")
    assert flags["values"] == {
        "demo_fallbacks": True,
        "strict": True,
        "embed_analytics": False,
    }
    sources = flags["sources"]
    assert sources.get("demo_fallbacks") == "cli"
    assert sources.get("strict") == "cli"
    assert sources.get("embed_analytics") == "cli"
    assert flags.get("webhook_enabled") is False
    assert flags.get("webhook_url_masked") is False
    assert flags.get("webhook_url_source") == "default"
    assert metadata.get("validation_engine") == VALIDATION_ENGINE_VERSION

    # Without CLI overrides the defaults should remain intact
    base = ControlStrategy(_spec())
    base_report = base.generate_report()
    base_metadata = base_report.get("metadata", {})
    base_flags = base_metadata.get("run_flags")
    assert base_flags["values"] == {
        "demo_fallbacks": DEMO_FALLBACKS_DEFAULT,
        "strict": STRICT_DEFAULT,
        "embed_analytics": EMBED_ANALYTICS_DEFAULT,
    }
    base_sources = base_flags["sources"]
    assert base_sources.get("demo_fallbacks") == "default"
    assert base_sources.get("strict") == "default"
    assert base_sources.get("embed_analytics") == "default"
    assert base_flags.get("webhook_enabled") is False
    assert base_flags.get("webhook_url_masked") is False
    assert base_flags.get("webhook_url_source") == "default"
    assert base_metadata.get("validation_engine") == VALIDATION_ENGINE_VERSION


def test_cli_help_lists_runtime_flags():
    parser = cli._build_parser()
    subparsers_actions = [
        action
        for action in getattr(parser, "_subparsers", None)._group_actions  # type: ignore[attr-defined]
        if isinstance(action, argparse._SubParsersAction)
    ]
    run_parser = subparsers_actions[0].choices["run"]
    help_text = run_parser.format_help()
    for flag in ("--demo-fallbacks", "--strict", "--no-embed-analytics"):
        assert flag in help_text
