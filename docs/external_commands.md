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
- `400 Bad Request` — `reason` in { run_id_mismatch, unknown_action, missing:<field>, queue_full, per_source_quota, rate_limited, timing:<reason>, circuit_breaker }

## Limits & Backpressure
All inbound commands are throttled by configurable limits:

```yaml
run:
  external:
    limits:
      queue_max_depth: 100
      per_source_quota: 40
      rate: {tokens: 3, refill_seconds: 2.0}
      circuit_breaker: {consecutive_rejects: 10, cool_down_seconds: 10.0}
```

**Rejection reasons**
`queue_full`, `per_source_quota`, `rate_limited`, `duplicate_roll`, `circuit_breaker`, `timing:<reason>`, `unknown_action`, `missing:<field>`, `run_id_mismatch`.

## Journal
Accepted/rejected commands recorded with:
`origin: external:<source>`, `correlation_id`, `timing_legal`, `executed`, and optional `rejection_reason`.

## Diagnostics
- `GET /health` → `{"status":"ok"}`
- `GET /run_id` → `{"run_id":"<active>"}`
- `GET /version` → `{"version":"<engine>","build_hash":"abcdef"}`

Examples:
```bash
curl http://127.0.0.1:8089/health
curl http://127.0.0.1:8089/run_id
curl http://127.0.0.1:8089/version
```

## Replay Mode

Set `run.external.mode` to `off`, `live`, or `replay`:

- `off` — disables inbound commands entirely.
- `live` — default; accepts HTTP commands and records them to the command tape.
- `replay` — replays commands from the tape deterministically. HTTP intake and webhooks are disabled; decisions are driven exclusively by the tape.

Configure the tape path via `run.external.tape_path` (or CLI flag `--command-tape-path`).
See `docs/command_tape.md` for format and usage.

## Webhook Topics

CSC can POST events to external systems:
- `run.started`
- `hand.started`
- `roll.processed`
- `hand.finished`
- `run.finished`

Set `run.webhooks.enabled=true` and optionally `run.webhooks.targets=["http://127.0.0.1:1880/webhook"]`.

Each payload includes:
```json
{"event":"roll.processed","run_id":"abc123","bankroll_after":950}
```

### Reliability

Webhooks retry up to two additional times with exponential backoff (250 ms then 500 ms plus jitter). A final failure logs a warning but does not interrupt the run.

### Server behavior
- If the uvicorn server cannot start (e.g., port in use), CSC logs the failure and falls back to the stdlib HTTP server automatically.
- Diagnostics endpoints (`/health`, `/run_id`, `/version`) are served by whichever server is active.
