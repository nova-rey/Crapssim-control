# CrapsSim Engine API Adapter

CSC ships with an optional HTTP engine adapter that allows runs to target the
CrapsSim Engine API instead of the in-process engine.

## Requirements

* The CrapsSim Engine API (``crapssim_api``) must be available and importable.
  Install from the API branch in editable mode or from a future PyPI release.
* A FastAPI/HTTP server exposing ``crapssim_api.http.router`` must be running.
  The adapter can also be used with a `fastapi.testclient.TestClient` during
  tests.

## CLI usage

```bash
csc run --spec spec.json --engine=http_api --engine-url=http://localhost:8000
```

Use ``--engine-timeout-seconds`` to adjust HTTP timeouts when needed. When the
CLI flag is omitted, the adapter defaults to ``CRAPSSIM_API_URL`` or
``http://localhost:8000``.

## Spec configuration

```yaml
run:
  engine: http_api
  engine_http:
    base_url: http://localhost:8000
    timeout_seconds: 10
```

Omitting ``run.engine`` keeps the legacy in-process engine path unchanged.

## Determinism notes

``HttpEngineAdapter`` forwards the run seed to ``/session/start``. Individual
rolls may also provide explicit dice via ``step_roll(dice=(d1, d2))``. This
allows CSC determinism tests to reproduce sequences by injecting dice into the
API when necessary.
