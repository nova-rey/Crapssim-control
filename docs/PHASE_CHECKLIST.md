# Phase Checklist

| Phase | Checkpoint | Title | ✅ | Summary |
|--------|-------------|-------|---|----------|
| P19·C0 | Docs Kickoff — DSL MVP | ✅ Complete | brief and constraints added |
| P19·C1 | Parser & Validation | ✅ Complete | WHEN/THEN parse, whitelist vars, errors |
| P19·C2 | Evaluator & Verbs | ✅ Complete | windows, cooldown, scope, conflict rule |
| P19·C3 | Controller Integration | ✅ Complete | flag-gated, legality gate, journaling |
| P19·C4 | Tests & Capabilities | ✅ Complete | seeded determinism, capabilities in report |
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
| P16·C3 | CLI & Config Sanity | ✅ Complete | version and schema printed on run |
| P16·C4 | Code Hygiene & Audit | ✅ Complete | Ruff/Black clean + CI green |
| P16·C5 | Final Baseline & Tag | ✅ Complete | LTS tag v1.0.0-lts captured |
| P15·C0 | Docs Kickoff & Guardrails | ✅ Complete | Activate Phase 15 and define orchestration scope and safety rules |
| P15·C1 | Control Surface Adapter | ✅ Complete | In-process start/stop/status wrapper and event publishing hooks |
| P15·C2 | Node-RED Webhook Bridge | ✅ Complete | HTTP endpoints (`/run/start`, `/run/stop`, `/status`) with SSE stream (`/events`) |
| P15·C3 | Live Event Stream Bus | ✅ Complete | Thread-safe queue-based event bus and SSE encoder |
| P15·C4 | Local UI Stub + Manifest View | ✅ Complete | Minimal HTML stub to watch events and query status |
| P15·C5 | Baseline & Tag | ✅ Complete | Capture Phase 15 baseline and write tag `v0.44.0-phase15-baseline` |
|   15  | C1         | Explain + decisions.csv |             | run --explain + decisions trace     |
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
