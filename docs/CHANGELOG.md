# Changelog

## v0.40.1-phase8.5-hotfix
- Stabilize effect summary logging: guarantee `"verb"` field present in every JSONL line.
- Standardize key order for `effect_summaries.jsonl` to reduce noisy diffs and simplify parsing.
- Doc note added under “Release Note — v0.40.1-phase8.5-hotfix”. No functional engine changes.

## v0.40.0-phase8-baseline
- Engine plumbing complete: live CrapsSim wiring for box/line/come/DC/odds under feature flag.
- Roll loop integrated: `step_roll()` drives engine dice; travel/PSO captured.
- Determinism: replay parity verified with fixed dice; seeded runs reproducible.
- Schemas frozen: `snapshot_schema: "2.0"`, `roll_event_schema: "1.0"`, `engine_contract_version: "1.0"`.
- Baseline artifacts produced via `simulate_rounds()` (generated locally; not committed).

## v0.35.0-phase6.5
- Adapter contract and Verb+Policy grammar frozen
- Effect/tape schema validation
- Capabilities endpoint includes schema versions
- Replay parity + digest check baselines added
- Deprecations: legacy "martingale" verb; NullAdapter shims scheduled for removal in Phase 8·C0

## [1.0.0] – 2025-09-19
### Added
- Stable public CLI: `crapssim-ctl` with `validate` and `run` subcommands.
- Spec validator with clear hard errors and soft warnings.
- YAML spec support (optional; JSON still works fine).
- Example strategy specs (`examples/minimal.json` and `.yaml`).
- Rules/Policy checklist documentation to help verify casino-accurate behavior.

### Changed
- Logging polish: consistent error and warning output; `-v`/`-vv` control verbosity.

### Docs
- Refreshed `README.md` quickstart and CLI usage.
- Tightened `SPEC.md` (clearer templates, rules structure, and event matching).

### Deferred (post-V1)
- Batch 4: Feature-flagged “levers” for aggressive/defensive presets.
- Batch 5: Live tuning hooks and granular telemetry.


# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] – 2025-09-19
### Added
- First public-ready V1: strategy spec validator, rules engine glue, CLI (`crapssim-ctl`).
- YAML or JSON spec loading, strict validation with friendly errors/warnings.
- Basic `run` wrapper around CrapsSim (when installed) with result summary.
- Documentation: `README.md`, `SPEC.md`.

### Changed
- CLI and logging polish (Batch 18): consistent error text, `-v / -vv` verbosity.

### Deferred (post-V1)
- Batch 4/5 “feature-flagged” extras (table presets & advanced odds helpers).
