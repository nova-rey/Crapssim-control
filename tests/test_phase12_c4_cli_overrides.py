import io
import json
import sys
from types import SimpleNamespace

from crapssim_control.cli import main


created_adapters = []


class DummyTable:
    def __init__(self):
        self.players = [SimpleNamespace(bankroll=1500.0)]

    def play(self, rolls: int | None = None, **_kwargs) -> None:
        self.last_rolls = rolls


class DummyAdapter:
    def __init__(self):
        self._policy_opts = {"enforce": True}
        created_adapters.append(self)

    def attach(self, spec):
        self.spec = spec
        return SimpleNamespace(table=DummyTable(), meta={})

    def enable_dsl_trace(self, *_args, **_kwargs):
        self.dsl_trace_enabled = True


def test_cli_overrides(tmp_path, monkeypatch):
    # Create minimal spec file
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps({"run": {"rolls": 5}}), encoding="utf-8")

    # Create sample risk policy file
    pol_file = tmp_path / "risk.yaml"
    pol_file.write_text(
        json.dumps({"run": {"risk": {"max_drawdown_pct": 10}}}),
        encoding="utf-8",
    )

    created_adapters.clear()

    monkeypatch.setattr("crapssim_control.engine_adapter.EngineAdapter", DummyAdapter)
    monkeypatch.setattr(
        "crapssim_control.engine_adapter.resolve_engine_adapter",
        lambda: (DummyAdapter, None),
    )
    monkeypatch.setattr("crapssim_control.cli._capture_control_surface_artifacts", lambda *a, **k: None)
    monkeypatch.setenv("CSC_SKIP_VALIDATE", "1")

    # Fake args
    test_args = [
        "run",
        str(spec_file),
        "--max-drawdown",
        "25",
        "--max-heat",
        "200",
        "--bet-cap",
        "place_6:90",
        "--recovery",
        "flat",
        "--risk-policy",
        str(pol_file),
    ]
    monkeypatch.setattr(sys, "argv", ["csc"] + test_args)

    # Capture stdout
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)

    try:
        main()
    except SystemExit:
        pass

    out = buf.getvalue()
    assert "Risk policy active" in out
    assert "max_drawdown_pct" in out
    assert "max_heat" in out
    assert "bet_cap_place_6" in out
    assert "recovery_mode" in out

    assert created_adapters, "Expected adapter to be instantiated"
    adapter = created_adapters[0]
    assert adapter._policy_overrides["max_drawdown_pct"] == 25.0
    assert adapter._policy_overrides["max_heat"] == 200.0
    assert adapter._policy_overrides["bet_cap_place_6"] == 90.0
    assert adapter._policy_overrides["recovery_mode"] == "flat_recovery"
    assert adapter._risk_policy.max_drawdown_pct == 25.0
    assert adapter._risk_policy.max_heat == 200.0
    assert adapter._risk_policy.bet_caps["place_6"] == 90.0
    assert adapter._risk_policy.recovery.mode == "flat_recovery"
