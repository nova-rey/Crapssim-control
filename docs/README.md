# CrapsSim-Control (CSC) v3 — Phase 9 Complete

> Status: Phase 11 (Strategy DSL v1) in progress — docs initialized; implementation begins at C1.

CSC now supports **every vanilla bet type** through its engine adapter, journaling, and reporting layers.

## Quick Demo

csc run –spec examples/example_line_odds.json –export

This produces:
- `journal.csv`
- `summary.json`
- `manifest.json` (includes schema + capabilities)
