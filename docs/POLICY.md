# Project Policies

## Validation & Errors
- **Hard errors**: fail validation, printed under `failed validation:` with bullet points.
- **Soft warnings**: allowed; shown when `-v`/`-vv` and logged as warnings.

CLI expectations:
- `validate` success: stdout contains `OK: <path>`
- `validate` failure: exit 2, stderr starts with `failed validation:` then bullets
- `run` failure when CrapsSim missing: exit 2, friendly message
- Verbosity (`-v`, `-vv`) controls log level

## Backward Compatibility
- Keep error texts stable when tests assert on them.
- YAML/JSON both supported; no YAML-only constructs required.

## Release Notes
- Update `CHANGELOG.md` per release.