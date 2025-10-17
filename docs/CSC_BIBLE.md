# CrapsSim-Control Bible
A living chronicle of design intent, reasoning, and phase outcomes.

---

## Preface
This document complements `CSC_SNAPSHOT.yaml`.  
Where the snapshot tracks *state*, the Bible records *story*—why decisions were made and what was learned.

---

## Phase 0 — Staging & Safeguards
**Date:** 2025-10-16  
**Objective:** Introduce flags, schema labels, and hygiene with zero behavioral change.  

**Highlights**
- Added runtime flags:  
  - `run.demo_fallbacks=false`  
  - `run.strict=false`  
  - `run.csv.embed_analytics=true`  
- Embedded `journal_schema_version` and `summary_schema_version` (1.1).  
- Strengthened `.gitignore`; purged caches.  
- CI tests remained green throughout.  

**Artifacts**
- Baselines captured under `baselines/phase0/` via `capture_baseline_p0c3.sh`.  
- Tag: `v0.29.0-phase0-baseline`.

**Notes**
- This phase builds the foundation for guarded evolution.  
- No runtime logic altered; repo clean.  

---

## Phase 1 — Defaults & Nuisance Removal (Active)
**Checkpoint P1·C1 — Disable demo fallbacks by default (Complete)**
- Default for `run.demo_fallbacks` set to `false` via centralized config helpers.
- Added backwards-compatible coercion in `spec_validation` so legacy truthy strings stay valid.
- Controller prints a one-time startup notice and exposes the default in report metadata.
- Tests cover the new default/off and explicit `true` path to guard regressions.

**Checkpoint P1·C2 — CLI flag wiring (Complete)**
- CLI `--demo-fallbacks`, `--strict`, and `--no-embed-analytics` now map directly to `run.*` config overrides.
- Controller metadata reports the effective flag set (`run_flags`) so reports capture CLI influence.
- Tests assert defaults remain unchanged, CLI overrides mutate the spec, and run reports surface final values.

---

## Agent-Mode Transition (October 2025)
Beginning with Phase 1, CrapsSim-Control enters full Agent-mode development.

- Repo entrypoint: `NOVA_AGENT_ENTRYPOINT.yaml`
- Agent responsibilities: mechanical edits, tests, doc updates.
- Human (Rey) responsibilities: planning, reasoning, approvals.
- Documentation hierarchy standardized under `/docs/`.
- Commit / tag / checkpoint discipline enforced via automated workflow.

Phase 0 closed at `v0.29.0-phase0c3-baseline` with deterministic CI verification.

# CrapsSim-Control Bible  
**Version 3 Runtime Development Narrative**

---

## Phase 0 Summary — Staging & Safeguards (Complete)
Phase 0 established a safe, deterministic baseline with inert feature flags and schema labeling.
- Added config flags: `run.demo_fallbacks`, `run.strict`, `run.csv.embed_analytics`
- Introduced schema versioning: `journal_schema_version`, `summary_schema_version`
- Hardened `.gitignore`, cleaned caches
- Captured deterministic baseline (`baselines/p0c3/`)
- CI verified and tagged `v0.29.0-phase0c3-baseline`

Outcome: Stable and reproducible foundation for Phase 1.

---

## Phase 1 Overview — Defaults & Nuisance Removal (Active)
**Objective:** Shift from prototype-safe defaults to production-safe behavior while maintaining full backward compatibility.

**Goals**
1. Turn off demo fallbacks by default.
2. Add CLI flags for explicit control (`--demo-fallbacks`, `--strict`).
3. Embed `validation_engine: "v1"` in output.
4. Verify both fallback modes produce valid results.
5. Tag stable baseline `v0.29.1-phase1-preflight`.

**Design Guardrails**
- No deep refactors.
- Each checkpoint passes CI independently.
- One Agent run per checkpoint.
- Preserve deterministic reproducibility.

---

## Agent-Mode Protocol (Ongoing)
- Entrypoint: `NOVA_AGENT_ENTRYPOINT.yaml`
- Documentation roots: `/docs/`
- Commit format: `P<phase>C<checkpoint>: <title>`
- Tag end-of-phase: `v0.<minor>.0-phase<phase>-baseline`
- Agents handle mechanics (code edits, tests, CI).
- Rey handles reasoning, approvals, and planning.

---

**Current Tag:** `v0.29.0-phase0c3-baseline`  
**Next Tag:** `v0.29.1-phase1-preflight`

