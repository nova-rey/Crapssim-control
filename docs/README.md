# CrapsSim-Control (CSC) v3 — Phase 9 Complete

> Status: Phase 9 complete. Phase 9.1 (Transport Abstraction) in progress — docs initialized; code unchanged.

CSC now supports **every vanilla bet type** through its engine adapter, journaling, and reporting layers.

## Quick Demo

csc run –spec examples/example_line_odds.json –export

This produces:
- `journal.csv`
- `summary.json`
- `manifest.json` (includes schema + capabilities)
