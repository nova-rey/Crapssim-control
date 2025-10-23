# Phase Checklist

| Phase | Checkpoint | Title | ✅ | Summary |
|--------|-------------|-------|---|----------|
| P12 | C0 | Docs Kickoff & Roadmap Sync | ✅ Complete | Sync docs and roadmap for new phase start |
| P12 | C1 | Risk Policy Schema & Loader | ✅ Complete | Define schema, defaults, and loader for risk settings |
| P12 | C2 | Policy Engine Core | ✅ Complete | Implement logic for evaluating caps, drawdown, heat, and recovery gates |
| P12 | C3 | Integration with Runtime | ☐ | Intercept outgoing actions and annotate journal entries with policy outcomes |
| P12 | C4 | CLI Flags & Spec Overrides | ✅ Complete | Added CLI overrides for drawdown, heat, bet caps, and recovery; manifest logs risk_overrides |
| P12 | C5 | Validation & Baseline | ☐ | Run seeded scenarios; confirm tagging; tag v0.43.0-phase12-baseline |
| P12·C6 | Validation Baseline & Phase Wrap | ✅ Complete | Validated early-stop and risk policy parity, captured seeded baseline, tagged v0.44.0-phase12-baseline |
| P12·C5a | Early Termination (Bankroll/Unactionable) | ✅ Complete | Stop the run when bankrupt or no legal bet can be placed; journal & manifest record termination |
| P12·C6p | Surface Wiring & Parity Fixes | ✅ Complete | Added missing CLI flags, report/manifest fields, and a parity test for Phase 12 metadata |

## Future Proposed Phases
- P13 — Integrated Spec Builder & Chained Runs.
- P14 — TBD.
