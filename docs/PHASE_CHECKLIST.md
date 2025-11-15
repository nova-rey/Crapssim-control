# Phase Checklist

### Phase 10 — Engine API Integration (HTTP)

| Checkpoint | Title                                   | Status | Summary |
|-----------|-------------------------------------------|--------|---------|
| P10·C1    | HTTP Engine Adapter Implementation        | ✅     | Added HttpEngineAdapter, factory wiring, manifest/journal metadata, and tests. |
| P10·C2    | CLI & Docs Surface for Engine API         | ✅     | Added ENGINE_API_ADAPTER.md and documented configuration, endpoints, determinism. |
| P10·C3    | Determinism / Parity Harness              | ✅     | Added test harness for forced-dice parity between inprocess and HTTP engine. |
| P10·C4    | Baseline Artifacts (HTTP Engine)          | ✅     | Captured seeded baseline run artifacts for HTTP engine mode. |
| P10·C5    | Tag v0.41.0-phase10-baseline              | ✅     | Baseline tagged for fully integrated HTTP engine support. |


### Phase 19 — DSL MVP (Deterministic Behavior Switching)

| Checkpoint | Title                                              | Status | Summary |
|------------|----------------------------------------------------|--------|---------|
| P19·C0     | Docs Kickoff & Roadmap Sync                        | ✅      | Initialized documentation updates for Phase 19. |
| P19·C1     | DSL Schema & Parser                                | ✅      | WHEN/THEN syntax, condition grammar, and argument parsing. |
| P19·C2     | Deterministic Evaluator                            | ✅      | Snapshot-only evaluation, legal windows, guard handling. |
| P19·C3     | Journaling & Decision Trace                        | ✅      | decisions.csv/JSONL with applied/rejected and trace reasons. |
| P19·C4     | DSL MVP Documentation Sync                         | ✅      | Updated snapshot, entrypoint, and Bible entries. |

| Phase | Checkpoint | Title | ✅ | Summary |
|--------|-------------|-------|---|----------|
| P18·C0 | Docs Kickoff — Evo Job Intake | ✅ Complete | Add File-Drop + HTTP job specs |
| P18·C1 | Lane A — File-Drop Watcher | ✅ Complete | jobs/incoming → runs/*_results + receipts |
| P18·C2 | Lane B — HTTP Job Queue | ✅ Complete | POST /runs + GET /runs/{id}, idempotent |
| P18·C3 | Docs + Examples | ✅ Complete | usage snippets and config knobs |
| P17·C0 | Docs Kickoff (Evo Bundle I/O) | ✅ Complete | roadmap + checklist entries for bundle I/O |
| P17·C1 | Bundle Export (CSC → Evo) | ✅ Complete | export_bundle() zips manifest/report/journal/decisions |
| P17·C2 | Bundle Import (Evo → CSC) | ✅ Complete | import_evo_bundle() reads/normalizes spec, verifies schemas |
| P17·C3 | Docs & Patch Tag | ✅ Complete | Bible entry and version bump to 1.0.1-lts |
| P16·C0 | Docs Kickoff & Guardrails | ✅ Complete | freeze new features and define LTS criteria |
| P16·C1 | Performance & Memory Profiling | ✅ Complete | profiling tools added under tools/ |
| P16·C2 | Schema Freeze & Validation | ✅ Complete | journal/summary schemas locked to v1.1 |
| P16·C3 | CLI Fossil Cleanup & Artifact Lock Test | ✅ Complete | Removed legacy EngineAdapter code and added regression test ensuring per-run artifacts are generated |
| P16·C4 | Code Hygiene & Audit | ✅ Complete | Ruff/Black clean + CI green |
| P16·C5 | Final Baseline & Tag | ✅ Complete | LTS tag v1.0.0-lts captured |
| P15·C0 | Docs Kickoff & Guardrails | ✅ Complete | Activate Phase 15 and define orchestration scope and safety rules |
| P15·C1 | Control Surface Adapter | ✅ Complete | In-process start/stop/status wrapper and event publishing hooks |
| P15·C2 | Node-RED Webhook Bridge | ✅ Complete | HTTP endpoints (`/run/start`, `/run/stop`, `/status`) with SSE stream (`/events`) |
| P15·C3 | Live Event Stream Bus | ✅ Complete | Thread-safe queue-based event bus and SSE encoder |
| P15·C4 | Local UI Stub + Manifest View | ✅ Complete | Minimal HTML stub to watch events and query status |
| P15·C5 | Baseline & Tag | ✅ Complete | Capture Phase 15 baseline and write tag `v0.44.0-phase15-baseline` |
| P15·C2d | Per-run artifacts finalizer + strict-exit | ✅ Complete | Writes `summary.json` / `manifest.json` always; exits non-zero on validation failure (unless --no-strict-exit). |
|   15  | C1         | Explain + decisions.csv | ✅ Complete | run --explain + decisions trace     |
|   15  | C2         | Human summary + init + doctor | ✅ Complete | summarize --human; init skeleton quick run |
| P16·V1 | API v1 hardening & UI prep | ✅ Complete | Versioned routes, CORS/auth, runs list/detail, replay, static UI hook |
| P14·C0 | Docs Kickoff & Guardrails | ✅ Active | Initialize Phase 14 docs and guardrails |
| P14·C1 | Plugin Manifest & Registry | ✅ Complete | Manifest schema and registry foundation established |
| P14·C2 | Safe Loader & Sandbox Lite | ✅ Complete | Restricted loader with deny-lists and timeouts |
| P14·C3 | Runtime Binding (verbs & policies) | ✅ Complete | Resolve, sandbox-load, register, and manifest-trace plugins declared by a run |
| P14·C4 | Conveyor Integration & Isolation | ✅ Complete | Per-run plugin roots, manifest snapshot, and registry cleanup |
| P14·C5 | CLI & Example Plugins | ☐ Pending | Plugin tooling and example package |
| P13·C0 | Docs Kickoff & Roadmap Sync | ✅ Complete | Sync docs and roadmap for new phase start |
| P13·C1 | Batch Runner Skeleton | ✅ Complete | Add batch execution mode with per-run exports |
| P13·C2 | Sweep Plans & Aggregation Glue | ✅ Complete | Plan format + batch index summary |
| P13·C3 | Reports v2 (per-run) | ✅ Complete | ROI, drawdown, PSO rate, by-family digest |
| P13·C4 | Batch Leaderboard & Comparators | ✅ Complete | Leaderboard, CSV, deltas, correlations |
| P13·C5 | Baseline & Tag | ✅ Complete | Capture seeded baseline and tag release |

## Future Proposed Phases
