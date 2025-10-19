| Phase | Checkpoint | Title | Status | Summary |
|-------|-------------|-------|---------|----------|
| P8·C0 | Docs Kickoff & Roadmap Update | ✅ Complete | Replace old Phase 6 roadmap with new Phase 8 roadmap and mark prior phases as future. |
| P8·C1 | CrapsSim Wiring (press/regress) + Snapshot Normalizer + Seed Handoff | ✅ Complete | Engine-backed press/regress under flag; seed handoff; minimal normalizer. |
| P8·C2 | Place/Buy/Lay Wiring | ✅ Complete | Engine-backed place/buy/lay/move/take_down; full box coverage; normalized bet_types. |
| P8·C3 | Line & Come Family + Odds Wiring | 🟡 In Progress | Line (pass/don’t), Come/DC, and Odds verbs wired; snapshot captures flats and odds by point. |
| P8·C4 | Roll & Travel Synchronization | 🟡 In Progress | Wire step_roll to CrapsSim’s dice engine; update snapshot and journaling; detect travel, PSO, and bankroll changes. |
| P8·C5 | Roll Loop Integration + Dice Control | ⬜ Pending | Implement step_roll through engine and fixed dice replay. |
| P8·C6 | Snapshot Normalizer v2 (Comprehensive) | ⬜ Pending | Expand normalizer to full table/player state. |
| P8·C7 | Error Surface & Journaling Consistency | ⬜ Pending | Map engine errors and enforce effect_summary validation. |
| P8·C8 | Replay Parity (Engine-backed) + Tape Additions | ⬜ Pending | Verify live vs replay parity using engine-derived snapshots. |
| P8·C9 | Performance Pass & Memory Sniff | ⬜ Pending | Run throughput tests and collect basic perf data. |
| P8·C10 | Capability Expansion & Introspection Lock | ⬜ Pending | Expose full control surface via /capabilities. |
| P8·C11 | Deprecation Cleanup & Toggle Safety | ⬜ Pending | Remove legacy martingale and legacy shims; maintain flags. |
