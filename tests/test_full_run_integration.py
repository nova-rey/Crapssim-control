import json
import os

import pytest

from crapssim_control.controller import replay_run, simulate_rounds
from crapssim_control.engine_adapter import VanillaAdapter

crapssim = pytest.importorskip("crapssim")


def _live_adapter():
    adapter = VanillaAdapter()
    adapter.start_session({"run": {"adapter": {"live_engine": True}}})
    return adapter


def _stub_adapter():
    adapter = VanillaAdapter()
    adapter.start_session({"run": {"adapter": {"live_engine": False}}})
    return adapter


def _with_cwd(path):
    class _Cwd:
        def __enter__(self):
            self._prev = os.getcwd()
            os.chdir(path)
            return path

        def __exit__(self, exc_type, exc, tb):
            os.chdir(self._prev)

    return _Cwd()


def test_full_run_live_creates_artifacts(tmp_path):
    adapter = _live_adapter()
    with _with_cwd(tmp_path):
        result = simulate_rounds(adapter, rolls=10, seed=123)
        assert os.path.exists("baselines/baseline_run_journal.csv")
        assert result["summary"]["rolls"] == 10


def test_replay_parity(tmp_path):
    adapter = _live_adapter()
    with _with_cwd(tmp_path):
        simulate_rounds(adapter, rolls=10, seed=777)
        with open("baselines/baseline_run_summary.json", encoding="utf-8") as handle:
            digest_live = json.load(handle)

    adapter_replay = _live_adapter()
    with _with_cwd(tmp_path):
        replay = replay_run(adapter_replay, "baselines/baseline_run_journal.csv")
        assert abs(digest_live["bankroll_end"] - replay["bankroll_end"]) < 1e-6


def test_fallback_mode_stable(tmp_path):
    adapter = _stub_adapter()
    with _with_cwd(tmp_path):
        result = simulate_rounds(adapter, rolls=5, seed=5)
        assert result["summary"]["rolls"] == 5
        replay = replay_run(adapter, "baselines/baseline_run_journal.csv")
        assert replay["rolls"] == 5
