# Phase Checklist

| Phase | Checkpoint | Title | Status | Summary |
|------:|:----------:|-------|:------:|---------|
| P9.1·C0 | Repo Sync (Transport Abstraction Mini-Phase) | ✅ Complete | Initialized Phase 9.1 docs; no code changes |
| P9.1·C1 | EngineTransport + LocalTransport | ✅ Complete | Adapter now delegates to transport interface |
| P9.1·C2 | Capability Handshake (Engine-Aware) | ☐ Pending | Probe engine, merge into /capabilities + manifest |
| P9.1·C3 | Conformance Suite + API Proposal | ☐ Pending | Transport-param tests and engine_api_proposal.md |
| P9.1·C4 | HTTP Transport Stub (Optional) | ☐ Pending | Wire stub client for future CrapsSim API |
| P9·C0 | Repo Sync (Phase 9 Kickoff) | ✅ Complete | Phase 9 initialized, Phase 8 marked complete |
| P9·C1 | Come/DC Odds + Field + Hardways | ✅ Complete | Live engine verbs and snapshot coverage added |
| P9·C2 | One-Roll Props Integration | ✅ Complete | Added Any7/AnyCraps/Yo/2/3/12/C&E/Hop verbs; one-roll props & journaling. |
| P9·C3 | ATS + Capability Truthfulness | ✅ Complete | Integrated ATS bets and added capability reporting |
| P9·C4 | Error Surface Polish + Replay/Perf Sanity | ✅ Complete | Standardized error codes, replay parity, and performance metrics |
| P9·C5 | Docs & Examples Pack (Phase 9 Closeout) | ✅ Complete | Documentation and examples finalized for all vanilla bets |
| P9·WRAP | Phase 9 Wrap Hotfix | ✅ Complete | Version bump, capability flags truthfulness, tolerant ATS mapping |
| P8·C1 | CrapsSim Wiring (press/regress) + Snapshot Normalizer + Seed Handoff | ✅ Complete | Engine-backed press/regress; seed handoff; normalization v1. |
| P8·C2 | Place/Buy/Lay Wiring | ✅ Complete | Engine-backed place/buy/lay/move/take_down; box bets normalized. |
| P8·C3 | Line & Come Family + Odds Wiring | ✅ Complete | Pass/Don’t, Come/DC, and Odds wired; flats/odds per point in snapshot. |
| P8·C4 | Roll & Travel Synchronization | ✅ Complete | step_roll integrated; travel & PSO recorded; journaling extended. |
| P8·C5 | Full System Integration & Baseline | ✅ Complete | simulate_rounds + replay harness; schemas frozen; baseline tag. |
| P8·C5a | Live Engine Wiring — Line/Come/Odds Hotfix | ✅ Complete | Route line/come/odds to engine; bankroll deltas engine-derived; snapshot reflects flats/odds. |

## Future Proposed Phases
- P10 — Web Dashboard MVP.
- P11 — Run Launcher & Spec Library.
- P12 — Integrated Spec Builder & Chained Runs.
