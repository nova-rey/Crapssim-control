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


⸻