# CrapsSim-Control — Phase 0 Checkpoint 3  
### Baseline Capture & Verification

**Date:** YYYY-MM-DD  
**Owner:** Rey / Nova  
**Snapshot Tag:** v0.29.0-phase0-baseline  

---

## 🎯 Objective
Capture baseline artifacts (journal CSV, report JSON, manifest JSON) for Phase 0 with zero behavioral change.

---

## 🧭 Scope
**In:**  
- `scripts/capture_baseline_p0c3.sh` creation and CI integration  
- Artifact verification and storage under `baselines/phase0/`  

**Out:**  
- Any runtime or schema edits beyond labeling  

---

## 🧪 Plan of Record
1. Pre-flight – ensure `pytest -q` is green  
2. Run agent for mechanical steps  
3. Verify artifacts exist and match expected hash sizes  
4. Commit and tag `v0.29.0-phase0-baseline`  
5. Update `CSC_SNAPSHOT.yaml` and append Bible chapter  

---

## ⚙️ Agent Task List
- [ ] Make `scripts/capture_baseline_p0c3.sh` executable  
- [ ] Run script to produce baseline artifacts  
- [ ] Verify output files in `baselines/phase0/`  
- [ ] Run `pytest -q` → green  
- [ ] Commit with message: `P0C3: Capture baseline artifacts`  

---

## ✅ Exit Criteria
- [ ] All tests green  
- [ ] Artifacts captured and logged  
- [ ] No runtime behavior change  
- [ ] Snapshot and Bible updated

- [ ] # Phase 0 — Staging & Safeguards ✅

| Checkpoint | Task | Status |
|-------------|------|--------|
| P0·C1 | Flag framework | ✅ Complete |
| P0·C2 | Schema labels | ✅ Complete |
| P0·C3 | Hygiene & baseline snapshot | ✅ Complete |

Baseline tag: `v0.29.0-phase0c3-baseline`  
CI: Green ✅

---

# Phase 1 — Defaults & Nuisance Removal (Next)
**Upcoming Checkpoints**
1. P1·C1 — Disable demo fallbacks by default  
2. P1·C2 — Add `--demo-fallbacks` / `--strict` CLI flags  
3. P1·C3 — Add `validation_engine: "v1"` to CLI/report  
4. P1·C4 — Dual-mode demo spec verification (fallback ON/OFF)  
5. P1·C5 — Tag `v0.29.1-phase1-preflight`

- [ ] Tag created and pushed  
