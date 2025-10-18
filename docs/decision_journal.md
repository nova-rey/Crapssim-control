# Decision Journal (v1)

All rule evaluations and actions are recorded here.

## Safeties
- Cooldowns: prevent refire within N rolls.
- Once-per-scope: block repeated triggers per hand/session.
- Duplicate blocking: same verb not queued twice in one roll.

## Format
Each record includes:
timestamp, run_id, hand_id, roll_in_hand, rule_id, action, timing_legal,
cooldown_remaining, executed, result, origin, note.

## Files
- JSONL: `decision_journal.jsonl`
- Optional CSV export via `DecisionJournal.to_csv("decision_journal.csv")`
