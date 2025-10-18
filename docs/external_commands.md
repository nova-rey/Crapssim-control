# External Commands (Phase 6)

CSC exposes a minimal HTTP API for external brains (e.g., Node-RED).

## Endpoint
`POST /commands` — accepts a JSON command and queues it for execution at the next legal timing window.

### Payload
```json
{
  "run_id": "abc123",
  "action": "switch_profile",
  "args": {"name": "Recovery"},
  "source": "node-red@flow-01:v1",
  "correlation_id": "nr-1234-0001"
}

Responses
	•	202 Accepted — queued
	•	400 Bad Request — rejected with reason (run_id_mismatch, unknown_action, duplicate_correlation_id, missing:<fields>)

Journal

All accepted and rejected commands are logged in decision_journal.jsonl with:
origin: external:<source>, correlation_id, timing_legal, executed, and optional rejection_reason.
