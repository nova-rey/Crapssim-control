import pytest

pytest.importorskip("crapssim_api.http")
pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from crapssim_api.http import router

from crapssim_control.engine.http_api_adapter import HttpEngineAdapter
from crapssim_control.testing.engine_parity import run_parity_test
from crapssim_control.engine.factory import build_inprocess_engine_adapter
from crapssim_control.config import RunConfig


def test_parity_harness_runs_basic_sequence():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    http_adapter = HttpEngineAdapter(
        base_url="http://testserver",
        client=client,
    )

    inprocess = build_inprocess_engine_adapter(RunConfig())

    http_adapter.start_session({}, seed=123)
    inprocess.start_session({}, seed=123)

    dice_stream = [(1, 1), (3, 2), (4, 3), (6, 1), (2, 2)]

    results = run_parity_test(inprocess, http_adapter, dice_stream, steps=5)

    assert len(results) == 5
    for entry in results:
        assert "inprocess" in entry
        assert "http_api" in entry
