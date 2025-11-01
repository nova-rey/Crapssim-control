# CSC Audit — P15·C2d Finalizer & Per-Run Artifacts

## Environment
- Python 3.12.10 on Linux 6.12.13 (x86_64).【ae9620†L2】【ee81e6†L2】
- ruff 0.12.11; black 25.1.0 (compiled); pytest 8.4.1.【08da99†L2】【8b8e63†L1-L2】【b988d0†L1】

## Static Wiring (Code Structure)
- csc alias: **PASS** — `csc/__main__.py` re-exports `crapssim_control.cli:main`.【F:csc/__main__.py†L1-L7】
- io_atomic.write_json_atomic: **PASS** — atomic temp-write + `os.replace` implemented in `crapssim_control/utils/io_atomic.py`.【F:crapssim_control/utils/io_atomic.py†L1-L13】
- decisions_trace.output_dir: **PASS** — `DecisionsTrace.__init__` stores `self.output_dir = pathlib.Path(folder)` before opening `decisions.csv`.【F:crapssim_control/run/decisions_trace.py†L1-L40】
- run_cmd finalizer present (try/finally): **PASS** — `_finalize_per_run_artifacts` writes summary/manifest/journal【F:crapssim_control/commands/run_cmd.py†L43-L100】 and `cli.run` always invokes it inside a `finally:` block that also closes the decisions trace.【F:crapssim_control/cli.py†L1475-L1489】

## CLI Help
- `python -m csc --help` exposes `summarize`, `init`, `doctor`, `run`, `dsl`, `journal` and documents `--explain`.【e331dd†L1-L23】
- `python -m csc run --help` shows required flags including `--explain`.【6a22b6†L1-L34】
- `python -m crapssim_control.cli --help` mirrors the alias output.【6c65b8†L1-L20】

## Scenario A — Happy Path
- Command: `python -m csc run --spec spec.json --seed 4242 --explain` (exit 0).【dd6d08†L1-L2】
- Run directory: `/tmp/tmp.kF9JZMEu52/artifacts/f59022b3c90e415ebda76c258aac780e` (single folder under `artifacts/`).【7448bc†L1-L2】
- Assertions: `decisions.csv` has 2 lines (header + data); `summary.json` and `manifest.json` parse cleanly via JSON load.【571e62†L1-L3】【8e383b†L1-L2】【fc6671†L1-L10】

## Scenario B — Export-free Path
- Command: `python -m csc run --spec spec.json --seed 777 --explain` (exit 0).【f2e4c1†L1-L2】
- Run directory: `/tmp/tmp.cBcEBUDdpk/artifacts/df1ee75e1db7466fa19877ca024a82e1` (single folder).【7dd263†L2-L3】
- Assertions: `decisions.csv` has 2 lines; `summary.json` and `manifest.json` parse cleanly.【f22ea1†L1-L11】【a6dc04†L1-L9】

## Scenario C — Failure-adjacent
- Command: `python -m csc run --spec bad_spec.json --seed 111 --explain` against intentionally invalid spec (exit code 0 despite validation errors).【9be1e1†L1-L4】【6c8903†L1-L2】
- Run directory: `/tmp/tmp.opuYnBwDRZ/artifacts/6e010e3b7de7433a86aa6ed8b1321145` materialized with fallback artifacts.【456ba5†L1-L2】【19caea†L1-L5】
- Assertions: `summary.json` and `manifest.json` parse, even though the run failed validation; `decisions.csv` contains fallback summary row only.【69d233†L1-L14】【6bf7d6†L1-L9】

## Human Summary
- `python -m csc summarize --artifacts ... --human` created `report.md` beside Scenario A run artifacts.【21469f†L1-L3】
- `report.md` is non-empty; first lines reference the artifacts path and flags. Generated summary derives from controller data (no fallback marker).【368eb2†L1-L10】【c262d9†L1-L2】

## Lint / Style / Tests
- `ruff check .` — All checks passed.【5811e2†L1-L2】
- `black --check .` — All files already formatted.【0e8aa4†L1-L2】
- `pytest -q` — 429 passed, 3 skipped (warnings only).【18ab97†L1-L66】

## Docs Alignment
- CSC Bible documents Phase 15 C2d finalizer guarantee in append-only history.【F:docs/CSC_BIBLE.md†L888-L910】
- Usage guide highlights `python -m csc …` alias and parity with `python -m crapssim_control.cli`.【F:docs/USAGE_HAPPY_PATH.md†L1-L9】
- Phase checklist lists Phase 15 C1/C2 rows but does not yet include a row for C2d status (gap).【F:docs/PHASE_CHECKLIST.md†L24-L38】

## Verdict
- Finalizer present: **YES** (try/finally wiring confirmed).
- Per-run summary/manifest guaranteed: **YES** (observed across successful, export-free, and validation-failure runs).
- Action Items:
  - **Low:** Consider updating `docs/PHASE_CHECKLIST.md` to explicitly track Phase 15 · C2d completion for parity with CSC Bible.
  - **Low:** Investigate why `csc run` returns exit code 0 even when validation errors abort execution, in case non-zero exit is expected for failed specs.
