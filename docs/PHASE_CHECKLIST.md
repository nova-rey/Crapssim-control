# Phase Checklist

| Phase | Checkpoint | Title | Status | Summary |
|------:|:----------:|-------|:------:|---------|
| P8·C1 | CrapsSim Wiring (press/regress) + Snapshot Normalizer + Seed Handoff | ✅ Complete | Engine-backed press/regress; seed handoff; normalization v1. |
| P8·C2 | Place/Buy/Lay Wiring | ✅ Complete | Engine-backed place/buy/lay/move/take_down; box bets normalized. |
| P8·C3 | Line & Come Family + Odds Wiring | ✅ Complete | Pass/Don’t, Come/DC, and Odds wired; flats/odds per point in snapshot. |
| P8·C4 | Roll & Travel Synchronization | ✅ Complete | step_roll integrated; travel & PSO recorded; journaling extended. |
| P8·C5 | Full System Integration & Baseline | ✅ Complete | simulate_rounds + replay harness; schemas frozen; baseline tag. |
| P8·C5a | Live Engine Wiring — Line/Come/Odds Hotfix | ✅ Complete | Route line/come/odds to engine; bankroll deltas engine-derived; snapshot reflects flats/odds. |

## Future Proposed Phases
- P9 — Control Surface & Diagnostics (work/off toggles, capability introspection, error surface polish, perf sanity, deprecation cleanup).
- P10 — Web Dashboard MVP.
- P11 — Run Launcher & Spec Library.
- P12 — Integrated Spec Builder & Chained Runs.
