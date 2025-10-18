## Phase 2 — Single-Source Runtime Consolidation

| Checkpoint | Title | Status | Notes |
|-------------|--------|--------|-------|
| P2·C1 | File Moves + Shims (No Logic Changes) | ✅ Complete | Renamed *_rt modules to canonical names with import shims. |
| P2·C2 | Delete Redundancies (Guarded) | ✅ Complete | Removed legacy modules with no inbound references and added regression test. |
| P2·C3 | Import Hygiene + Deprecation Log | ✅ Complete | Replaced all *_rt imports with canonical module names and added centralized deprecation registry. |
| P2·C4 | Spec Loader Shim (Key Normalization) | ✅ Complete | Spec key normalization + deprecations recorded. |
| P2·C5 | Baseline & Tag | ✅ Complete | Baseline artifacts captured; tagged v0.30.0-phase2-baseline. |

---

**Phase 2 Status:** ✅ Complete  
**Baseline Tag:** `v0.30.0-phase2-baseline`  
Artifacts captured in `baselines/phase2/` (journal.csv, report.json, manifest.json).  

## Phase 3 — Analytics & Journal Integration

| P3·C1 | Analytics Hook Scaffolding | ✅ Complete | Introduced analytics package with Tracker/Ledger stubs. |
| P3·C2 | Bankroll & Roll Tracking Integration | ✅ Complete | Added optional CSV columns: hand_id, roll_in_hand, bankroll_after, drawdown_after. |
| P3·C3 | Summary Expansion | ✅ Complete | Report now includes analytics summary fields and summary_schema_version "1.2". |
| P3·C4 | Journal Schema Versioning | ✅ Complete | Added journal_schema_version "1.2" to CSV/report outputs; centralized constants in schemas.py. |
| P3·C5 | Baseline & Tag | ✅ Complete | Captured seeded analytics run and tagged v0.31.0-phase3-baseline. |

**Phase 3 Status:** ✅ Complete
**Baseline Tag:** `v0.31.0-phase3-baseline`

## Phase 4 — Control Surface & Integrations

| Checkpoint | Title | Status | Summary |
|-------------|--------|---------|----------|
| P4·C0 | Docs Kickoff & Roadmap Setup | ✅ Complete | Update docs for Phase 4 structure and visibility. |
| P4·C1 | CLI Flag & Manifest Framework | ✅ Complete | Unified CLI flag handling and added standardized run-manifest schema. |
| P4·C2 | Node-RED / Webhook Stub Integration | ✅ Complete | Opt-in lifecycle POST hooks with safe defaults and masked config. |
| P4·C3 | Runtime Report & Metadata Polish | ✅ Complete | Added run_id/manifest_path, engine & artifacts blocks, and flag provenance; webhooks carry run_id. |
| P4·C4 | Evo Integration Hooks (Scaffold) | ✅ Complete | Added EvoBridge stub and manifest evo block for future CrapsSim-Evo interoperability. |
| P4·C5 | Baseline & Tag | ✅ Complete | Captured seeded integration baseline and tagged v0.32.0-phase4-baseline. |

| Phase | Title | Status | Tag | Notes |
|-------|--------|---------|------|-------|
| 5 | CSC-Native Rules Engine (Internal Brain) | ⏳ In Progress | v0.34.0-phase5-ittt | Deterministic rule evaluation and decision journaling. |
| 6 | Node-RED Driven Control (External Brain) | ⏳ Planned | v0.35.0-phase6-external | External command interface, unified decision journal. |
| 7 | Web Dashboard MVP | ⏳ Planned | v0.36.0-phase7-baseline | Live monitoring, run history, artifacts. |
| 8 | Run Launcher & Spec Library | ⏳ Planned | v0.37.0-phase8-baseline | /runs API and spec management. |
| 9 | Integrated Spec Builder & Chained Runs | ⏳ Planned | v0.38.0-phase9-baseline | Unified builder, chained run support. |

## Phase 5 — CSC-Native Rules Engine (Internal Brain)

| Checkpoint | Title | Status | Notes |
|-------------|--------|--------|-------|
| P5·C1 | Rule Schema & Evaluator (Read-Only) | ✅ Complete | Added rule DSL and deterministic evaluator; no actions yet. |
| P5·C2 | Action Catalog & Timing Guards | ✅ Complete | Implemented canonical verbs and legality checks. |
| P5·C3 | Decision Journal & Safeties | ✅ Complete | Added cooldowns, once-per-scope, and structured logging. |
| P5·C4 | Spec Authoring Aids | ✅ Complete | Added macro expansion and lint tooling for authoring rule specs. |
