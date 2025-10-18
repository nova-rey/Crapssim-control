# Rule Authoring Aids (v1)

Macro expansion and linting utilities for building rule specs.

## Macros
Defined in YAML files under `macros:`. Parameters use `$param` placeholders.

Example:
```yaml
macros:
  bankroll_guard:
    when: "bankroll_after < $threshold"
    action: "switch_profile('$profile')"
```

Use with:
```yaml
use: bankroll_guard
params:
  threshold: 500
  profile: Recovery
```

## Linting

Run:
```bash
csc --lint-rules strategy.yaml --macros templates/core_macros.yaml
```

Checks for:
- Unknown variables
- Unknown verbs
- Duplicate IDs
- Schema compliance
