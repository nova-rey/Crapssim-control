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
