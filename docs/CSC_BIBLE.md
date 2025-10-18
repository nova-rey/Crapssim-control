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
- Embedded `journal_schema_version` and `summary_schema_version` (1.2).
- Strengthened `.gitignore`; purged caches.  
- CI tests remained green throughout.  

**Artifacts**
- Baselines captured under `baselines/phase0/` via `capture_baseline_p0c3.sh`.  
- Tag: `v0.29.0-phase0-baseline`.

**Notes**
- This phase builds the foundation for guarded evolution.  
- No runtime logic altered; repo clean.  

---

## Phase 1 — Defaults & Nuisance Removal (Complete)
**Checkpoint P1·C1 — Disable demo fallbacks by default (Complete)**
- Default for `run.demo_fallbacks` set to `false` via centralized config helpers.
- Added backwards-compatible coercion in `spec_validation` so legacy truthy strings stay valid.
- Controller prints a one-time startup notice and exposes the default in report metadata.
- Tests cover the new default/off and explicit `true` path to guard regressions.

**Checkpoint P1·C2 — CLI flag wiring (Complete)**
- CLI `--demo-fallbacks`, `--strict`, and `--no-embed-analytics` now map directly to `run.*` config overrides.
- Controller metadata reports the effective flag set (`run_flags`) so reports capture CLI influence.
- Tests assert defaults remain unchanged, CLI overrides mutate the spec, and run reports surface final values.

**Checkpoint P1·C3 — Validation-engine labeling (Complete)**
- Introduced `VALIDATION_ENGINE_VERSION = "v1"` and surfaced it in `report.json` metadata.
- CLI run header now prints `validation_engine: v1` to make validator provenance obvious in logs.
- New regression test guards the constant, report value, and CLI emission for future bumps.

**Checkpoint P1·C4 — Docs sync + example refresh (Complete)**
- Updated quick-start docs to reflect disabled demo fallbacks, strict validation defaults, and analytics toggles.
- Refreshed quickstart example spec to opt in to demo fallbacks explicitly.
- Synced report schema documentation with `validation_engine: "v1"` metadata.

**Checkpoint P1·C5 — Terminology polish & provenance metadata (Complete)**
- Refined CLI/docs terminology so Guardrails references only appear when strict mode is enabled and default flows speak to Advisories.
- Embedded `validation_engine` and the full run flag provenance map under `metadata`, capturing both effective values and whether they came from defaults, the spec, or CLI overrides.


### Phase 2 — Single-Source Runtime Consolidation

**Purpose:**  
Unify the runtime under one canonical module path, retire duplicates safely, and prepare for analytics integration (Phase 4). No behavioral changes — only structural cleanup.

**Checkpoint 1 (P2·C1): File Moves + Shims**  
RT modules renamed to canonical names with deprecation shims in place.

**Checkpoint 2 (P2·C2): Delete Redundancies (Guarded)**  
Removed unused legacy modules (`events_std.py`, `materialize.py`, `memory_rt.py`, `snapshotter.py`) after confirming no inbound references.  
Added regression test to ensure deleted modules are not reintroduced.  
System behavior remains identical.

**Checkpoint 3 (P2·C3): Import Hygiene + Deprecation Log**  
All imports now reference canonical runtime modules (`templates`, `rules_engine`, `legalize`).  
A centralized Deprecation Registry (`deprecations.py`) issues one-time warnings for legacy shim imports.  
Behavior unchanged — only warning management and import clarity improved.

**Checkpoint 4 (P2·C4): Spec Loader Shim (Key Normalization)**
Added a load-time normalization pass that migrates deprecated spec keys to
their canonical names, prefers modern fields when both are present, and records
each migration under `report.metadata.deprecations` for easy auditing.

**Checkpoint 5 (P2·C5): Baseline & Tag**
Baseline artifacts captured and tagged `v0.30.0-phase2-baseline`.

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

**Current Tag:** `v0.30.0-phase2-baseline`  
**Next Tag:** `TBD`


#### Phase 2 Closure — Baseline & Tag

A clean end-to-end run was captured following runtime consolidation and key normalization.  
Baseline artifacts — `journal.csv`, `report.json`, and `manifest.json` — are stored under `baselines/phase2/`.  
This marks the successful completion of the Single-Source Runtime Consolidation phase, ensuring one canonical runtime path with backward-compatible shims, centralized deprecation logging, and automatic spec-key normalization.  
Tagged release: **v0.30.0-phase2-baseline**.

### Phase 3 — Analytics & Journal Integration

**Purpose:**  
Integrate the analytics layer directly into the CSV journaling system, ensuring bankroll continuity and attribution for every roll and hand. This phase reconnects the unified runtime from Phase 2 with the legacy Tracker/Ledger analytics logic, updated for deterministic tracking.

**Checkpoint 1 (P3·C1): Analytics Hook Scaffolding**
Created a new `analytics/` module containing stub classes for `Tracker` and `Ledger`.
The controller now calls `on_session_start`, `on_hand_start`, `on_roll`, and `on_hand_end` events only when `run.csv.embed_analytics=True`.
No data is yet written to CSV; this provides the structural foundation for later bankroll and roll tracking.

**Checkpoint 2 (P3·C2): Bankroll & Roll Tracking Integration**
Tracker now records live bankroll and roll context. When `run.csv.embed_analytics=True`, each CSV row includes:
- hand_id
- roll_in_hand
- bankroll_after
- drawdown_after

These fields are additive only. With the flag off, CSV outputs remain byte-for-byte identical to the Phase 2 baseline.

**Checkpoint 3 (P3·C3): Summary Expansion**
The end-of-run report now aggregates analytics from the tracker:
`total_hands`, `total_rolls`, `points_made`, `pso_count`, `bankroll_peak`, `bankroll_low`, and `max_drawdown`.
`summary_schema_version` is set to `"1.2"`. Gameplay math and CSV rows remain unchanged; this checkpoint is reporting-only.

**Checkpoint 4 (P3·C4): Journal Schema Versioning**

Both CSV and report outputs now include explicit schema version labels (`journal_schema_version` and `summary_schema_version`, both "1.2").  
A central `schemas.py` file defines these constants to keep exports and documentation aligned.

**Checkpoint 5 (P3·C5): Baseline & Tag**

A deterministic analytics-enabled run was captured as the Phase 3 baseline.  
Artifacts include CSVs, reports, and manifests with and without analytics.  
All schema versions set to "1.2".  
Tagged release: **v0.31.0-phase3-baseline**.

> Note: When `run.csv.embed_analytics=false`, analytics fields in the summary may be zero or omitted.
> The `summary_schema_version` remains `"1.2"` for compatibility.

## Phase 4 — Control Surface & Integrations

Purpose: Extend CrapsSim-Control outward. This phase focuses on interface polish and external linkages — CLI ergonomics, Node-RED/webhook scaffolds, and metadata clarity for downstream systems like CrapsSim-Evo.

### Checkpoints
- **P4·C0 — Docs Kickoff & Roadmap Setup:** Establish Phase 4 structure and roadmap visibility.
- **P4·C1 — CLI Flag & Manifest Framework:** Unify CLI flags and implement a standard run-manifest schema.
- **P4·C2 — Node-RED / Webhook Stub Integration:** Introduce minimal communication stubs for orchestration.
- **P4·C3 — Runtime Report & Metadata Polish:** Refine report readability and metadata consistency.
- **P4·C4 — Evo Integration Hooks (Scaffold):** Lay foundation for CrapsSim-Evo interop (no coupling yet).
- **P4·C5 — Baseline & Tag:** Capture seeded integration baseline and tag v0.32.0-phase4-baseline.

### Checkpoint 1 — CLI Flag & Manifest Framework

This checkpoint standardized how CLI flags are parsed and stored.  
It introduced `cli_flags.py` for consistent defaults and `manifest.py` for generating a structured `manifest.json` alongside each export.  
The manifest enables external orchestration tools to read run metadata and schema versions without parsing reports directly.

### Checkpoint 2 — Node-RED / Webhook Stub Integration

Outbound lifecycle hooks (run/hand/roll) are available behind explicit flags. Defaults remain no-op. Payloads are intentionally small; failures never interrupt simulations. Sensitive configuration (webhook URL) is masked in reports and summarized in the manifest.

### Checkpoint 3 — Runtime Report & Metadata Polish

Reports now include `run_id`, `manifest_path`, and an `engine` and `artifacts` block under `metadata`.
Each run flag records a `*_source` indicating CLI/spec/default provenance.
All webhook payloads now include `run_id` (and seed/fingerprint on `run.started` when available) for downstream correlation.

### Checkpoint 4 — Evo Integration Hooks (Scaffold)

A new `EvoBridge` interface defines the minimal handshake points for future CrapsSim-Evo integration.
It is disabled by default and inert, writing optional stub logs for visibility.  
Manifest and CLI support `evo_enabled` and `trial_tag` fields, allowing downstream systems
to recognize and group trial cohorts without affecting simulation behavior.
