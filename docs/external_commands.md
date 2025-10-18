# External Commands (Phase 6)

## Endpoint
`POST /commands` — JSON body:
```json
{
  "run_id": "abc123",
  "action": "switch_profile",
  "args": {"name":"Recovery"},
  "source": "node-red@flow-01:v1",
  "correlation_id": "nr-1234-0001"
}
```

### Responses
- `202 Accepted` — queued
- `400 Bad Request` — `reason` in { run_id_mismatch, unknown_action, duplicate_correlation_id, missing:<fields>, bad_json }

## Journal
Accepted/rejected commands recorded with:
`origin: external:<source>`, `correlation_id`, `timing_legal`, `executed`, and optional `rejection_reason`.
