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
| P4·C1 | CLI Flag & Manifest Framework | ⏳ | Unify CLI flags; introduce run-manifest schema. |
| P4·C2 | Node-RED / Webhook Stub Integration | ⏳ | Add minimal hooks for external orchestration. |
| P4·C3 | Runtime Report & Metadata Polish | ⏳ | Expand metadata, improve report clarity. |
| P4·C4 | Evo Integration Hooks (Scaffold) | ⏳ | Lay down stub interfaces for CrapsSim-Evo. |
| P4·C5 | Baseline & Tag | ⏳ | Capture seeded baseline and tag v0.32.0-phase4-baseline. |
