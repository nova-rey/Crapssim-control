# Action Catalog (v1)

Defines canonical table-safe verbs and legality checks.

## Verbs
- `switch_profile(name)`
- `regress(pattern)`
- `press_and_collect(pattern)`
- `martingale(step_key, delta, max_level)`

## Timing Guards
Validated by `is_legal_timing(state, action)`:
- Blocks actions during resolution.
- Restricts some to come-out or post-resolution only.
- Logs reason for illegal attempts in `decision_journal.jsonl`.
