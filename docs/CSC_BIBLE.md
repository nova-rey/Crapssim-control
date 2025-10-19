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

### Checkpoint 5 — Baseline & Tag

Phase 4 closes with a seeded baseline capturing the complete Control Surface flow:
CLI flags → Manifest → Webhook → Report → Evo Scaffold.

Artifacts are stored under `baselines/phase4/`:
- `journal.csv`
- `report.json`
- `manifest.json`

This baseline serves as the reference point for Phase 6 external command integration.
Tag: **v0.32.0-phase4-baseline**.

---

## Phase 5 — CSC-Native Rules Engine (Internal Brain)

**Goal:** deterministic “if-this-then-that” strategy switching inside CSC, no network dependency.

### Checkpoints
1. **P5·C1 — Rule Schema & Evaluator (read-only)**
   JSON rule DSL: `when/scope/cooldown/guards/action/id`.
   Whitelisted vars: `bankroll_after`, `drawdown_after`, `hand_id`, `roll_in_hand`, `point_on`, `last_roll_total`, `box_hits[]`, `dc_losses`, etc.
   Deterministic evaluator returns decisions only.
2. **P5·C2 — Action Catalog & Timing Guards**
   Actions: `switch_profile`, `regress`, `press_and_collect`, `martingale(step_key, delta, max_level)`.
   Apply only at legal windows.
3. **P5·C3 — Decision Journal & Safeties**
   decisions.jsonl/csv with rule id, snapshot vars, action applied.
   Cooldowns and once-per-scope; conflict resolution.
4. **P5·C4 — Spec Authoring Aids**
   Rule templates/macros; validation with helpful errors.
5. **P5·C5 — Baseline & Tag**
   Seeded runs proving 3+ rule patterns. Tag `v0.34.0-phase5-ittt`.

### Checkpoint 5 — Baseline & Tag
Completed a seeded integration run demonstrating CSC’s internal rules engine.
Confirmed deterministic rule evaluation, timing guards, cooldowns, and decision journaling.
Artifacts stored under `baselines/phase5/`.
Tagged v0.34.0-phase5-ittt.

### Checkpoint 1 — Rule Schema & Evaluator (Read-Only)
Introduced a deterministic rule schema (JSON) and evaluator that checks rule conditions safely using a whitelisted expression parser.
Outputs candidate decisions for each roll/hand without mutating state.
This forms the foundation for CSC’s internal rules engine.

**Guardrails:** no `eval`; deterministic vars only; if not in the decision journal, it didn’t happen.

### Checkpoint 2 — Action Catalog & Timing Guards
Established CSC’s canonical action verbs and legality framework.
Rules now trigger queued actions that pass timing validation.
Each action records its legality and result in `decision_journal.jsonl`.

### Checkpoint 3 — Decision Journal & Safeties
Replaced ad-hoc decision logging with a formal Decision Journal system.
All rule evaluations and actions now produce standardized records with timestamps and safety status.
Safeties include cooldowns, once-per-scope locks, and duplicate blocking.

### Checkpoint 4 — Spec Authoring Aids
Introduced Rule Builder helpers so authors can compose rulesets in YAML with macros and parameters instead of hand-editing JSON.
The CLI now expands macros, substitutes `$param` placeholders, and performs lint checks for unknown variables, verbs, and schema regressions.
This makes the rule engine approachable while keeping validation strict before rules ever reach the evaluator.

---

## Phase 6 — Node-RED Driven Control (External Brain)

This phase extends CSC’s control surface so external systems like Node-RED can listen to CSC events and send back validated commands.  
All legality and timing remain enforced inside CSC; external brains never bypass safeguards.

### Roadmap
| Checkpoint | Title | Summary |
|-------------|--------|----------|
| **P6·C1** | Inbound Command Channel | Implement `/commands` endpoint with legality/timing enforcement and queuing. |
| **P6·C2** | Node-RED Flow | Example Node-RED flow that subscribes to CSC webhooks and issues commands. |
| **P6·C3** | Decision Journal Unification | Merge internal and external actions into one journal; add optional command tape. |
| **P6·C4** | Safety & Backpressure | Rate-limit and deduplicate external inputs; add deterministic replay mode. |
| **P6·C5** | Baseline & Tag | Demonstrate full external control loop and tag `v0.35.0-phase6-external`. |

### Goals
- Deterministic replays via recorded command tapes  
- Identical legality checks for both brains  
- Stable reporting schema (v1.2) maintained  
- Seamless path toward future dashboard integrations

### Checkpoint 1 — Inbound Command Channel
Established a minimal `/commands` HTTP endpoint with an internal queue. 
Commands include `run_id`, `action`, `args`, `source`, and `correlation_id`. 
CSC validates action verbs and timing; legal commands execute at the next window. 
All outcomes are recorded in the Decision Journal with `origin: external:<source>`.

### Checkpoint 1 — Inbound Command Channel
Added /commands HTTP intake with a deterministic queue. Commands validated for run_id, verb, and dedup by correlation_id. Applied at legal windows; all outcomes journaled with origin and correlation_id.

### Checkpoint 2 — Node-RED Flow (Listen → Decide → Command)
Added webhook publisher and demo Node-RED flow. CSC emits roll and hand events; flow listens and sends commands back to `/commands`. Introduced `run.http_commands.enabled` flag and timing-reject test.

Completed external-loop baseline proving webhooks → Node-RED → `/commands` → journal.
Added diagnostics endpoints (`/health`, `/run_id`) and verified timing rejections are recorded with explicit reasons.
Artifacts stored in `baselines/phase6/`.

### Checkpoint 3 — Decision Journal Unification (+ Command Tape & Replay)
Unified internal and external decision logging (shared fields and sequencing). Added a command tape recorder and deterministic replay mode.
Introduced a `/version` endpoint in diagnostics and lightweight webhook retries.
Artifacts stored under `baselines/phase6/unified_journal/`.

### Checkpoint 4 — Safety & Backpressure
Introduced external-command guardrails: queue depth, per-source quotas, token-bucket rate limiting, per-roll dedupe, and circuit breaker with cool-down/reset.
Standardized rejection reasons and added telemetry summary in report metadata.

### Checkpoint 5 — Baseline & Tag (v0.35.0-phase6-external)
Captured seeded external-control baseline with rate limits, dedupe, and circuit breaker active.
Validated deterministic replay and full journaling parity.
Diagnostics endpoints verified healthy.
Tagged v0.35.0-phase6-external.
- Diagnostics hardened: loud failure logs, automatic stdlib fallback, boot-time health probe, and clean shutdown; semantics for /commands unchanged.
