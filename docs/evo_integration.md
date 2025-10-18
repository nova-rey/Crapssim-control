# CrapsSim-Evo Integration Scaffold

## Overview
This checkpoint introduces a minimal scaffold for future CrapsSim-Evo interoperability.
Currently, EvoBridge is inert — it logs stub events when `--evo-enabled` is set.

## CLI Flags
- `--evo-enabled`: Activates EvoBridge stub logging.
- `--trial-tag <tag>`: Labels this run as part of a trial cohort.

## Manifest Additions
```json
"evo": {
  "enabled": true,
  "trial_tag": "cohort_A"
}
```

## Safety
- Disabled by default.
- No runtime behavior changes.
- All calls wrapped in try/except.
