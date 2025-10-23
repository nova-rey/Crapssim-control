import pytest


def mk_adapter(spec=None):
    from crapssim_control.engine_adapter import VanillaAdapter

    adapter = VanillaAdapter()
    base_run = {
        "policy": {"enforce": True},
        "journal": {"explain": False},
    }
    merged_spec = {"run": {}}
    merged_spec.update({k: v for k, v in (spec or {}).items() if k != "run"})
    run_block = merged_spec["run"]
    for key, value in base_run.items():
        run_block[key] = dict(value) if isinstance(value, dict) else value
    extra_run = (spec or {}).get("run", {})
    if isinstance(extra_run, dict):
        for key, value in extra_run.items():
            if isinstance(value, dict) and isinstance(run_block.get(key), dict):
                run_block[key].update(value)
            else:
                run_block[key] = value
    adapter.start_session(merged_spec)
    return adapter


def test_policy_blocks_illegal_and_journals(monkeypatch):
    spec = {
        "run": {
            "policy": {"enforce": True},
            "journal": {"explain": False},
            "risk": {"max_heat": 100},
        }
    }
    adapter = mk_adapter(spec)

    monkeypatch.setattr(
        adapter,
        "_snapshot_for_policy",
        lambda: {
            "bankroll": 1000,
            "bankroll_peak": 1000,
            "active_bets_sum": 9999,
            "previous_loss": 0,
        },
    )

    events = []
    from crapssim_control import journal as journal_mod

    monkeypatch.setattr(journal_mod, "_write_line", lambda line, **_: events.append(line))

    out = adapter.apply_action("place_6", {"amount": 60})
    assert out.get("status") == "rejected"
    assert any(
        isinstance(event, dict)
        and event.get("event") == "policy_eval"
        and event.get("risk_violation_reason")
        for event in events
    )


def test_policy_modified_recovery(monkeypatch):
    spec = {
        "run": {
            "policy": {"enforce": True},
            "journal": {"explain": False},
            "risk": {
                "max_heat": 1000,
                "recovery": {"enabled": True, "mode": "flat_recovery"},
            },
        }
    }
    adapter = mk_adapter(spec)

    monkeypatch.setattr(
        adapter,
        "_snapshot_for_policy",
        lambda: {
            "bankroll": 900,
            "bankroll_peak": 1000,
            "active_bets_sum": 10,
            "previous_loss": 50,
        },
    )

    called = {}

    def fake_apply(verb, call_args):
        called["args"] = call_args
        return {"ok": True}

    adapter.transport.apply = fake_apply

    adapter.apply_action("place_6", {"amount": 10})
    assert called["args"]["amount"] == 50


def test_passive_mode_allows_but_logs(monkeypatch):
    spec = {
        "run": {
            "policy": {"enforce": False},
            "journal": {"explain": False},
            "risk": {"max_heat": 100},
        }
    }
    adapter = mk_adapter(spec)

    monkeypatch.setattr(
        adapter,
        "_snapshot_for_policy",
        lambda: {
            "bankroll": 800,
            "bankroll_peak": 1000,
            "active_bets_sum": 9999,
            "previous_loss": 0,
        },
    )

    events = []
    from crapssim_control import journal as journal_mod

    monkeypatch.setattr(journal_mod, "_write_line", lambda line, **_: events.append(line))

    applied = {}
    adapter.transport.apply = lambda verb, call_args: applied.setdefault("ok", True) or {"ok": True}

    out = adapter.apply_action("place_6", {"amount": 60})
    assert out.get("status") != "rejected"
    assert any(
        isinstance(event, dict) and event.get("event") == "policy_eval"
        for event in events
    )


def test_summary_counters(monkeypatch):
    spec = {
        "run": {
            "policy": {"enforce": True},
            "journal": {"explain": False},
            "risk": {"max_heat": 100},
        }
    }
    adapter = mk_adapter(spec)

    monkeypatch.setattr(
        adapter,
        "_snapshot_for_policy",
        lambda: {
            "bankroll": 1000,
            "bankroll_peak": 1000,
            "active_bets_sum": 9999,
            "previous_loss": 0,
        },
    )
    adapter.apply_action("place_6", {"amount": 100})

    monkeypatch.setattr(
        adapter,
        "_snapshot_for_policy",
        lambda: {
            "bankroll": 1000,
            "bankroll_peak": 1000,
            "active_bets_sum": 0,
            "previous_loss": 0,
        },
    )
    adapter.transport.apply = lambda verb, call_args: {"ok": True}
    adapter.apply_action("place_6", {"amount": 10})

    summary = {}
    manifest = {}

    from crapssim_control import report_builder as rb

    rb.apply_policy_summary_fields(summary, adapter)
    rb.apply_policy_manifest_fields(manifest, adapter)

    assert summary["risk_violations_count"] >= 1
    assert manifest["risk_policy_version"] == "1.0"
