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
- [ ] Tag created and pushed  