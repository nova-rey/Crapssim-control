⸻

CHANGELOG.md

# Changelog

All notable changes to this project will be documented here.

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