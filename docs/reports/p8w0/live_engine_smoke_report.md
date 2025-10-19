# P8·W0 — Live Engine Smoke Report (CrapsSim)

## 1. Workspace & Environment
- **Python:** `Python 3.12.10` within a fresh venv (`python3 -m venv .venv`).【7c40e6†L1-L3】
- **pip:** `pip 25.0.1` (Python 3.12).【7c40e6†L3-L4】
- **CSC Install:** `crapssim-control==0.19.0` in editable mode from this repo (`pip install -e .`).【218d67†L1-L10】
- **Engine Install:** `crapssim==0.3.2` fetched from GitHub (`pip install git+https://github.com/skent259/crapssim.git`).【4c0c11†L1-L10】
- **Dependency snapshot:** `docs/reports/p8w0/pip-freeze.txt` (see Appendix).

## 2. Engine Probe (Capabilities Discovery)
- `import crapssim` succeeded; package does not expose `__version__` (reported `null`).【ce0790†L1-L43】
- Detected symbols:
  - `crapssim.table.Table`
  - `crapssim.table.Dice`
  - `crapssim.dice.Dice`
  - `crapssim.strategy` module present
  - `crapssim.players` module **missing** in this build
- JSON probe output:
  ```json
  {
    "crapssim_version": null,
    "symbols": {
      "crapssim.dice.Dice": true,
      "crapssim.players": false,
      "crapssim.strategy": true,
      "crapssim.table.Dice": true,
      "crapssim.table.Table": true
    }
  }
  ```

## 3. Adapter Modes
Test spec variants live under `docs/reports/p8w0/` and share the Martingale golden ruleset with a seeded 20-roll session.

### A. Adapter OFF — `run.adapter.enabled=false`
- Spec: `martingale_pass_adapter_off.json` (NullAdapter).【F:docs/reports/p8w0/martingale_pass_adapter_off.json†L1-L64】
- Command: `python -m crapssim_control run ...adapter_off.json`
- Result: 20 rolls, bankroll ended at **$994.00**; run completed without adapter telemetry (baseline behavior).【19c10e†L1-L86】

### B. Adapter ON — `run.adapter.impl="vanilla"`
- Spec: `martingale_pass_adapter_on.json` (VanillaAdapter, same seed 13579).【F:docs/reports/p8w0/martingale_pass_adapter_on.json†L1-L64】
- Command: `python -m crapssim_control run ...adapter_on.json`
- Result: Identical 20-roll transcript ending at **$994.00**, confirming deterministic parity between adapter off/on for this seed and ruleset.【8fbfc2†L1-L86】

## 4. HTTP Capabilities Surface
Using the in-repo FastAPI shim, the `/capabilities` handler responds with sorted schema and verb metadata when the app is instantiated:
```json
{
  "status_code": 200,
  "data": {
    "schema_versions": {"effect": "1.0", "tape": "1.0"},
    "verbs": ["apply_policy", "press", "regress", "same_bet", "switch_profile"],
    "policies": ["martingale_v1"]
  }
}
```
【73e458†L1-L19】

## 5. Action Grammar Smoke (VanillaAdapter)
Executed a tape-schema-1.0 command bundle against `VanillaAdapter`:
```json
{
  "tape_schema": "1.0",
  "results": [
    {"verb": "press", "bankroll": 994.0, "bets": {"6": 6.0, "8": 0.0, "pass": 0.0, "dc": 0.0}},
    {"verb": "press", "bankroll": 982.0, "bets": {"6": 6.0, "8": 12.0, "pass": 0.0, "dc": 0.0}},
    {"verb": "regress", "bankroll": 991.0, "bets": {"6": 3.0, "8": 6.0, "pass": 0.0, "dc": 0.0}}
  ],
  "snapshot": {
    "bankroll": 991.0,
    "point_on": false,
    "bets": {"6": 3.0, "8": 6.0, "pass": 0.0, "dc": 0.0},
    "hand_id": 0,
    "roll_in_hand": 0,
    "rng_seed": 0,
    "levels": {},
    "last_effect": {"verb": "regress", ...}
  }
}
```
【5be1bf†L1-L17】

## 6. Notes & Observations
- CrapsSim 0.3.2 omits an `__version__` attribute despite pip metadata providing the release number; downstream tooling should rely on package metadata instead of module globals.【ce0790†L1-L43】【4c0c11†L1-L10】
- The bundled FastAPI shim passes the request object positionally, so naive use of `fastapi.testclient.TestClient` raises a signature mismatch; direct handler invocation works for capability verification.【024073†L1-L20】【73e458†L1-L19】

## Appendix
- Dependency snapshot: [`pip-freeze.txt`](pip-freeze.txt)
