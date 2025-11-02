## Human Summary & Scaffolding
```bash
python -m csc init myrun && cd myrun
python -m csc doctor --spec spec.json
python -m csc run --seed 4242 --spec spec.json --explain
python -m csc summarize --artifacts artifacts/latest --human
```

> ℹ️ `python -m crapssim_control.cli ...` remains available and behaves the same as the `python -m csc ...` alias.

### Exit codes

- `0`  = Run completed successfully or with only advisory warnings.
- `1`  = Validation failure or unrecoverable runtime error.

Use `--no-strict-exit` if you wish to suppress the validation-error exit for exploratory runs.

## Web UI (since P16·C1)
Launch the minimal dashboard:
```bash
python -m csc ui --host 127.0.0.1 --port 8088
```

Open http://127.0.0.1:8088/ui. From there you can list runs, validate a spec, launch a run with --explain, and view/download per-run artifacts. The UI is a thin layer over the CLI, so results are identical to command-line usage.

## API v1 & UI Prep

All HTTP endpoints are now versioned under **`/api/v1/*`**. The legacy `/api/*` remains temporarily with a deprecation notice.

### Auth & CORS
- Optional bearer token via env: `CSC_API_TOKEN="..."`
- CORS allowlist via env: `CSC_CORS_ORIGINS="http://localhost:1880,http://127.0.0.1:5173"`

### Runs & Replay
- `GET /api/v1/runs?limit=25&cursor=<last_id>` → recent runs (id, state, artifact presence)
- `GET /api/v1/runs/{id}` → run status + artifact pointers
- `GET /api/v1/runs/{id}/replay?rate=5hz&max_events=200` → sampled journal events for UI replay

### Spec & Graph
- `POST /api/v1/spec/normalize` → normalized CSC spec v1
- `POST /api/v1/spec/to_graph` → canonical `csc.graph.v1` for visualization

### Optional Static UI
If a built web UI bundle exists at `./ui_static/` (or env `CSC_UI_STATIC_DIR`), CSC serves it at **`/ui/*`**.
