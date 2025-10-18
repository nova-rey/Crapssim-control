⸻


# CrapsSim-Control (CSC) — V3 Master History & Technical Archive
**Maintainer:** Rey  
**Compiled by:** Nova  
**Date:** October 2025  
**Version Target:** v0.30.0 — “Converged Runtime”  

---

## 🧭 Purpose
This document is a full historical and technical record for CrapsSim-Control.  
It contains everything needed to understand what was built in **V1** and **V2**, what worked, what didn’t, and exactly how **V3** will unify it all.  
If every other file vanished, this would be enough to rebuild CSC from scratch.

---

# 1. ARCHITECTURE AND CAPABILITIES (ACTUAL V2 CODE BASE)

### Overview
- **Version:** `crapssim_control 0.20.0`
- **Primary entry points:**
  - CLI (`validate`, `run`, `journal-summarize`)
  - Python API (`ControlStrategy`, `render_template`, `apply_rules`, `CSVJournal`, `summarize_journal`, `write_summary_csv`)
- **Spec model:** `table` + `variables` + `modes/templates` + `rules` + optional `run/export` blocks.

---

## 1.1 CLI TOOLS
| Command | Function |
|:--|:--|
| `validate <spec>` | Schema + policy check via `spec_validation.py`. Prints notes + warnings; no enforcement yet. |
| `run <spec>` | Loads strategy, seeds RNGs, attaches controller to CrapsSim engine, runs N rolls. Outputs streaming CSV journal + summary. |
| `journal-summarize` | Aggregates journal(s) into a compact summary CSV (totals, counts, mode switches, regressions, etc.). |

---

## 1.2 SPEC MODEL & VALIDATION
**Sections:**
- `table` – bubble/level/odds policy/increments  
- `variables` – arbitrary constants used in templates/rules  
- `modes` – templates of bets for each state  
- `rules` – event-driven logic  
- `run` – execution and export options  

**Validation Behavior:** lenient; warns, rarely hard-fails.

---

## 1.3 RUNTIME PIPELINE
**Events:** standardized by `events.py` (comeout, point_established, roll, seven_out, bet_resolved, shooter_change, point_made).  
**Controller:** maintains mode, point, rolls_since_point, and variable state.  
**Flow:**  
`event → templates_rt → legalize_rt → rules_rt → merge actions → apply to table → journal`.  

**Demo fallbacks:**  
- auto-`place_6` on PE(6)  
- auto-regress on third roll  
*(useful for demos, but confusing — will be off in V3)*

---

## 1.4 CSV JOURNALING & SUMMARIES
- Streaming writer (`csv_journal.py`) logs one row per event.  
- End-of-run summary (`csv_summary.py`) adds totals and metadata.  
- Optional export bundle (`exports.py`) collects CSV + report + manifest.

**Current columns:**  
`ts,run_id,seed,event_type,point,rolls_since_point,on_comeout,mode,units,bankroll,source,id,action,bet_type,amount,notes,extra`

---

## 1.5 LEGALIZATION ENGINE
- `legalize.py` + `legalize_rt.py` enforce table rules:  
  - Place bet increments (6/8 → $6; 5/9/4/10 → $5).  
  - Bubble tables → $1 steps.  
  - Odds limited by policy (`3-4-5x`, `10x`, etc.).  
  - Lays scaled by potential win.  
- Acts as the sanity layer between spec and engine.

---

## 1.6 GUARDRAILS / ADVISORIES
- Implemented in `guardrails.py`.  
- Currently **advisory only** — emit notes; no runtime blocking.  
- Future strict mode will clip or block with journaled flags.

---

## 1.7 ANALYTICS SUITE (V1 HERITAGE)
- `tracker.py` – per-roll, per-hand counters.  
- `bet_ledger.py` – open/closed bet accounting.  
- `bet_attrib.py` – per-bet-type win/loss & PnL.  
- `tracker_histograms.py` – distributions of rolls/points.  
- `exports.py` – CSV/JSON export helpers.  

*Currently stand-alone; not hooked into CSV journal.*

---

## 1.8 REPORTING & EXPORTS
- `report.json` – identity, seed, bankroll, CSV path.  
- `manifest.json` – maps artifact paths.  
- `export_bundle()` – packs CSV + JSON + meta into folder or zip.

---

## 1.9 SAFE EXPRESSION EVALUATOR
- `eval.py` – AST-based safe math: + - * / comparisons and boolean ops.  
- Whitelisted helpers: `abs`, `min`, `max`, `floor`, `ceil`, `round`, `sqrt`, `log`, `log10`.  
- No attribute access; pure expressions only.

---

## 1.10 ENGINE ADAPTER
- Bridges Controller to CrapsSim runtime API.  
- Auto-detects new or legacy API; attaches correctly.  
- Includes demo fallback behavior (to be removed).

---

# 2. REPO CRITIQUE (V2 STATE)

### Strengths
- Solid core runtime; deterministic flow.  
- Good test coverage; modular event model.  
- Working CSV export + manifest system.  

### Problems
1. **Duplicate modules** (`*_rt.py` vs legacy).  
2. **Validator split** (`spec_validate.py` vs `spec_validation.py`).  
3. **Hidden demo behaviors enabled by default.**  
4. **Advisory guardrails misleadingly named.**  
5. **Dead helpers:** `events_std.py`, `materialize.py`, `memory_rt.py`, `snapshotter.py`.  
6. **Docs/tests referencing old APIs.**  
7. **CSV schema unversioned.**  
8. **Repo clutter:** `__pycache__` committed.

---

# 3. WHAT’S WORTH KEEPING FROM V1
✅ **Analytics core** (Tracker/Ledger/Attrib/Histograms)  
✅ **Legalization policy tables** – reliable math facts  
✅ **CLI shape** – commands and UX intact  
✅ **Docs + Examples** – conceptually sound  
✅ **Engine adapter** – handles API variance  

These components remain valid; we’ll integrate or modernize them in V3.

---

# 4. BRIDGE PLAN — V1 → V2 → V3

| Domain | V1 Artifact | V2 Runtime | V3 Action |
|:--|:--|:--|:--|
| Templates | `templates.py` | `templates_rt.py` | rename RT → `templates.py`, delete old |
| Rules | `rules.py` | `rules_rt.py` | rename RT → `rules_engine.py`, shim import |
| Legalizer | `legalize.py` + `legalize_rt.py` | same | merge into single `legalize.py` |
| Events | `events_std.py` | `events.py` | delete std |
| Validator | `spec_validate.py` | `spec_validation.py` | delete old |
| Adapter | `engine_adapter.py` | same | prune demo behavior |
| Analytics | tracker suite | same | connect to journal |
| CSV | csv_journal / summary | same | add schema versions + export flag |
| Docs | spec.md / rules.md | same | update for V3 |

---

# 5. ANALYTICS → CSV INTEGRATION PLAN

### 5.1 Per-Event Enrichment
New columns:

bankroll_after, drawdown_after, hand_id, roll_in_hand,
point_cycle, pso_flag, attrib_note

Each roll logs bankroll continuity, volatility, and bet attribution.

### 5.2 Summary Expansion

hands_played, rolls_total, points_set/made,
pso_count, peak_bankroll, max_drawdown,
time_above_water_pct, by_bet_type_digest

### 5.3 Schema Versioning
Add headers:

journal_schema_version: “1.2”
summary_schema_version: “1.2”
analytics_embedded: true

### 5.4 Implementation Hooks
- Controller calls `tracker.on_event()` → returns analytics dict.  
- CSV writer logs analytics fields.  
- Finalizer writes tracker.summary() into cover sheet.  

Result → every CSV becomes a complete financial ledger.

---

# 6. V3 MERGE & CLEANUP PLAN

### Phase A — Hygiene & Defaults
- Purge `__pycache__/` and cache artifacts.  
- Add strong `.gitignore`.  
- Demo fallbacks OFF by default (+ flag to enable).  
- Rename Guardrails → Advisories.  

### Phase B — Single-Source Modules
- Consolidate `legalize`, `templates`, `rules`.  
- Delete legacy duplicates.  
- Migrate tests to new modules.  

### Phase C — Spec Loader Shim
- Normalize legacy keys; log `report.deprecations`.  
- Example: `odds_working_on_comeout` → `working_on_comeout`.  

### Phase D — CLI Polish
- Add `--strict`, `--export`, `--demo-fallbacks`.  
- `--export` triggers `export_bundle()` (zip + manifest).  

### Phase E — Tests & Docs
- Golden round-trip test.  
- Add “Happy Path” tutorial.  
- Write V1→V2→V3 migration guide.  

---

# 7. MONEY TRACKING DETAILS

### Example CSV Excerpt

roll_id,roll_total,action,bet_type,amount,payout,
bankroll_after,drawdown_after
17,9,bet_resolved,place_6,12,14,1014,6
18,7,seven_out,clear_all,,,-,-,12
19,comeout,pass_line,10,,-,1004,12

### Example Summary Block

Final Bankroll: 1342
Net Profit: +342
Peak Bankroll: 1389
Max Drawdown: 74
Hands Played: 27
PSO Count: 3
By Bet Type: {pass_line:{wins:15,losses:12,pnl:+30}, place_6:{…}}

Bankroll continuity is now reconstructible from CSV alone.

---

# 8. REPO HYGIENE CHECKLIST
- Delete: `events_std.py`, `materialize.py`, `memory_rt.py`, `snapshotter.py`, `spec_validate.py`  
- Merge: `legalize_rt.py` → `legalize.py`  
- Rename: `templates_rt.py` → `templates.py`; `rules_rt.py` → `rules_engine.py`  
- Strengthen .gitignore: ignore `*.pyc`, `__pycache__`, `.pytest_cache`, `dist`, `build`, `*.egg-info`  
- Clean tests and docs accordingly.  

---

# 9. EXECUTION ORDER (TARGET ROADMAP)
1️⃣ Hygiene & defaults  
2️⃣ Module consolidation  
3️⃣ Validator unification  
4️⃣ Analytics integration  
5️⃣ CLI flag expansion  
6️⃣ Spec loader shim  
7️⃣ Docs & tests  

---

# 10. EXPECTED OUTCOME
- One canonical runtime path  
- Full money tracking in journal  
- Strict/advisory clarity  
- Clean exports with stable schemas  
- Deterministic, testable, and future-proof  

---

# 11. VERSION TAG AND MOTTO
**Version Tag:** `v0.30.0 (V3 Converged Runtime)`  
**Motto:** *“Cut the fat and make every roll count.”*  

---

# 12. CHANGE HISTORY AT A GLANCE

| Phase | Date | Theme | Outcome |
|:--|:--|:--|:--|
| V1 | Early 2025 | Foundation | Analytics prototype, multi-module runtime |
| V2 | Mid–Late 2025 | Runtime rebuild | RT core, CSV journaling added |
| V3 | Oct 2025 → | Convergence & Money Tracking | Unified runtime, analytics integrated, strict/advisory clarity |

---

### END OF DOCUMENT
*(If this file is all that survives, it contains the full design intent, lineage, and rebuild path for CrapsSim-Control.)*


⸻
