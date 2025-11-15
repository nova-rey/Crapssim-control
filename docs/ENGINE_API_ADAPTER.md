# CrapsSim HTTP Engine Adapter

CSC supports running simulations using the CrapsSim Engine API over HTTP in
addition to the default in-process engine. The HTTP engine is optional and
only activates when explicitly selected via configuration or CLI flags.

---

## Engine Selection

The run configuration supports the following engine modes:

- `inprocess` — default behavior; uses local CrapsSim engine.
- `http_api` — uses the CrapsSim Engine API via HTTP.

CLI example:

```bash
csc run --spec my_spec.json \
        --engine=http_api \
        --engine-url=http://localhost:8000

Config example:

run:
  engine: http_api
  engine_http:
    base_url: http://localhost:8000
    timeout_seconds: 10

If --engine-url is not provided, CRAPSSIM_API_URL may be used as fallback.

⸻

API Requirements

The HTTP engine requires a running instance of the CrapsSim Engine API (from
the API branch of the CrapsSim repository).

Endpoints used by CSC include:
	•	POST /session/start
	•	POST /session/step
	•	POST /session/action
	•	Optional snapshot or metadata endpoints

CSC discovers capability information from the API where available.

⸻

Determinism & Seeds

Two deterministic modes are supported:

Engine-controlled RNG

CSC supplies a session seed to the API. The engine rolls dice internally.

CSC-controlled dice (parity testing)

For parity validation, CSC can send explicit dice to /session/step when the
API supports forced dice input. This produces deterministic roll consistency
across engine types.

⸻

Journaling & Metadata

Runs using the HTTP engine include the following metadata:

"engine_info": {
  "type": "http_api",
  "name": "crapssim-api",
  "base_url": "<url>",
  "version": "<reported_or_unknown>",
  "capabilities_source": "api"
}

Journal CSV preamble annotates the engine type and origin.

⸻

Test Harness

CSC includes a small parity-validation harness that runs the same dice stream
through both the in-process engine and the HTTP engine to confirm that point
cycles, bankroll flows, and event structure align where supported.

⸻

Optional Dependency

If CrapsSim-API or FastAPI dependencies are missing, HTTP engine tests are
skipped. The adapter remains importable but cannot be selected without the
required dependencies.

---
