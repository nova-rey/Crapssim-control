# Phase 6 — Node-RED Driven Control (External Brain)

| Checkpoint | Title | Status | Description |
|-------------|--------|---------|-------------|
| P6·C1 | Inbound Command Channel | ✅ Complete | /commands endpoint + queue; non-blocking; journal records origin+correlation_id. |
| P6·C2 | Node-RED Flow | ✅ Complete | Seeded baseline captured (baselines/phase6/) with Node-RED loop and new diagnostics endpoints. |
| P6·C3 | Decision Journal Unification | ⏳ In Progress | Unified journal for internal + external, command tape + replay mode, diagnostics `/version`, webhook retry. |
| P6·C4 | Safety & Backpressure | ⏳ In Progress | Added rate limits, per-roll dedupe, queue quotas, circuit breaker, telemetry. |
| P6·C5 | Baseline & Tag | ✅ Complete | Self-contained live + replay baselines (in-process simulator), diagnostics hardened, summary metrics added, tag v0.35.0-phase6-external. |
