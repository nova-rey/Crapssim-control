# Command Tape

The command tape captures every external command that CSC evaluates. Each line is
JSON (JSON Lines format) with at least:

```json
{
  "ts": 1719878400.123,
  "run_id": "demo-run-001",
  "source": "node-red@demo",
  "action": "press_and_collect",
  "args": {"pattern": "mid-stairs"},
  "executed": true,
  "correlation_id": "nr-42"
}
```

Optional fields include `rejection_reason`, `hand_id`, `roll_in_hand`, and
`journal_seq` (the unified decision journal sequence number).

## Capture

- Tape recording is automatically enabled in live mode. Configure the path via
  `run.external.tape_path` (or CLI `--command-tape-path`).
- Every command (accepted or rejected) is appended after it is processed, so the
  tape reflects the exact outcome.

## Replay

Set the mode to `replay` to drive decisions from a tape:

```yaml
run:
  external:
    mode: replay
    tape_path: baselines/phase6/unified_journal/command_tape.jsonl
```

In replay mode:

- The HTTP `/commands` endpoint and webhooks are disabled.
- Commands are loaded from the tape (in order) and fed through the same legality
  checks used in live operation.
- Deterministic outcomes require the same spec and random seed as the original run.

To switch between live and replay via CLI flags:

```bash
python run_demo.py --command-tape-path=export/command_tape.jsonl --external-mode=replay
```

Replay runs still produce reports, manifests, and unified journals, making it
easy to diff against the original execution.
