# CSC Health Report — Phase 15 (C1–C2 Verification)

## Environment
- Python 3.12.10 on Linux 6.12.13.【005f68†L1-L1】【49095e†L2-L2】
- Tooling: ruff 0.12.11, black 25.1.0, pytest 8.4.1.【c60fac†L2-L2】【771c78†L1-L2】【c48b75†L1-L1】
- Repo minimums: Python ≥3.11; Black target py311; Ruff configured with line length 100.【8361b2†L1-L48】

## Tree & Layout Snapshot
- No `csc/` package directory present (expected per docs); CLI lives under `crapssim_control` instead.【a4164f†L1-L2】【931c9f†L1-L4】
- `docs/` contains `examples/` and historical reports; `tests/` includes a committed `__pycache__` directory; `examples/` hosts JSON specs and plugin demos; no top-level `recipes/` directory exists.【93428c†L1-L6】【0aed65†L1-L3】【57df72†L1-L4】【c4e01a†L1-L2】
- Red flags: repository root currently has ignored `__pycache__/` and `.pytest_cache/` directories from local runs, and the absence of a `csc/` module conflicts with documentation expectations.【beee67†L1-L17】【005f68†L1-L2】

## Lint & Style
- `ruff check .` → clean.【cd5193†L1-L2】
- `black --check .` → 337 files would be left unchanged.【573f4d†L1-L2】

## Test Summary
- `pytest -q` → 420 passed, 3 skipped, 158 warnings (primarily deprecations and pytest collection warnings); slowest tests not reported under `-q`.【342f62†L55-L83】

## P15·C1 — Explain + decisions.csv
- CLI help under `python -m csc` fails (`No module named csc`); the working entry point is `python -m crapssim_control.cli` showing `run` with `--explain`.【005f68†L1-L2】【576ad8†L1-L10】【483a3d†L1-L8】【5f1566†L1104-L1166】
- Static wiring: `ControlStrategy` accepts `explain` and `decisions_writer`, deriving CLI/spec sources, and instantiates `DecisionsTrace` with canonical headers; CLI flag parser sets `explain` provenance.【c16fc1†L125-L203】【972ffa†L1-L30】【568ef6†L6-L91】
- Smoke run (`python -m crapssim_control.cli run --seed 4242 --explain spec.json`) succeeded but produced empty `decisions.csv` files (0 lines) inside `artifacts/<run_id>/`, indicating the explain trace is not populated despite manifest flagging `run.flags.explain=true`.【b53bcb†L1-L126】【c58cd3†L1-L6】【1dfc34†L1-L2】【1a31c4†L1-L42】
- No manifest, summary, or journal materialized beside the artifacts run folders; only a global `export/` manifest/journal pair was generated via baseline capture, leaving `artifacts/<run_id>/` incomplete for explain mode.【c58cd3†L1-L6】【1a31c4†L1-L42】

## P15·C2 — Human Summary + Init + Doctor
- CLI help for `summarize`, `init`, and `doctor` is only available under `python -m crapssim_control.cli`; documentation references the non-existent `csc` module.【c7d2bd†L1-L7】【dad512†L1-L6】【5d13bf†L1-L5】【005f68†L1-L2】
- `init` scaffolds `spec.json`, `behavior.dsl.yaml`, and empty `profiles/` + `recipes/`; `doctor --spec` on the generated spec reports “[OK]” checks but the default spec lacks required sections for running without manual edits.【3cf3e3†L1-L2】【0634e0†L1-L7】【1724fb†L1-L3】【612f8b†L1-L4】
- Using the bundled `examples/quickstart_spec.json`, `run --explain` executes, yet the artifacts folder still lacks `summary.json` and `decisions.csv` data; consequently `summarize --human` fails (“summary.json not found”) and no `report.md` is generated.【b53bcb†L1-L126】【c58cd3†L1-L6】【907e7c†L1-L2】

## Docs Alignment
- Phase checklist rows for Phase 15 C1/C2 are present but their status columns are blank, contrasting with surrounding completed entries.【87fa41†L20-L33】
- Snapshot records Phase 15 checkpoint 2 as “Human summary + init + doctor” (active).【8e3303†L1-L5】
- CSC Bible documents Phase 15 C1/C2 feature intents, matching the requested capabilities.【5653b6†L888-L895】
- Usage Happy Path instructs `csc ...` commands, which misaligns with the actual `crapssim-ctl` entry point shipped in this repo.【44fa9c†L1-L7】

## Examples & Recipes
- `examples/` hosts multiple JSON specs, plugin demos, and scaffolding assets (e.g., `quickstart_spec.json`, Node-RED flows).【57df72†L1-L4】
- No repository-level `recipes/` directory exists despite docs suggesting one; only initialized projects (via `csc init`) create empty `recipes/` locally.【c4e01a†L1-L2】【0634e0†L1-L7】

## Artifacts & Manifest Sanity
- Explain-mode artifacts only contained empty `decisions.csv` files; no `summary.json`, `journal.csv`, or `manifest.json` were produced per run directory, so downstream tools lack required inputs.【c58cd3†L1-L6】【1dfc34†L1-L2】【907e7c†L1-L2】
- Baseline capture wrote to `export/` instead, producing `journal.csv`, `report.json`, `manifest.json`, and `plugins_manifest.json`, with manifest content reflecting `run.flags.explain=true` sourced from CLI.【7dd86e†L1-L1】【1a31c4†L1-L42】

## Repo Hygiene
- `.gitignore` excludes `artifacts/`, caches, `*.csv`, and `*.json`, but it also ignores all root-level `*.md` (including this report) which requires force-adding health reports; consider whitelisting project-level documentation outputs.【225309†L1-L29】
- No tracked large (>2 MB) files detected under `artifacts/` or `tests/`; generated caches (`__pycache__/`, `.pytest_cache/`) remain ignored.【9ea0ec†L1-L1】【beee67†L1-L17】

## Risks & Recommendations
- **High:** Explain mode fails to populate `decisions.csv` and per-run artifacts, blocking P15·C1 deliverables and causing summarize to error. Investigate controller trace writes and ensure manifests/journals accompany explain outputs.【1dfc34†L1-L2】【907e7c†L1-L2】
- **High:** CLI documentation and docs reference a `csc` module that is absent (`python -m csc` fails). Provide the expected module alias or update docs/usage paths to `crapssim-ctl` to avoid broken onboarding.【005f68†L1-L2】【44fa9c†L1-L7】
- **Medium:** Phase checklist rows for 15·C1 and 15·C2 lack completion status, leaving roadmap artifacts inconsistent with code reality.【87fa41†L20-L33】
- **Medium:** Initialized `spec.json` fails validation for required sections without manual edits; enhance scaffolder defaults or templates to produce runnable specs out of the box.【0634e0†L1-L7】【612f8b†L1-L4】
- **Low:** `.gitignore` blanket `*.md` rule complicates adding repo-root health reports; add explicit exceptions for governance outputs to streamline auditing.【225309†L1-L29】
