⸻

docs/DEV_WORKFLOW.md

CrapsSim-Control — Collaborative Development Workflow

Purpose: define how phases, checkpoints, and handoffs work between Rey and Nova. This document lives alongside the code as the project’s memory spine.

⸻

🧭 1. Guiding Principles
	•	Incremental, never brittle. Each change should be small enough to roll back with one commit.
	•	State is sacred. The CSC_SNAPSHOT.yaml file is the single source of truth for where we are.
	•	One brain, two modes.
	•	Chat Mode → design, reasoning, and decision log.
	•	Agent Mode → mechanical execution (edits, tests, exports).
	•	Phase ≈ one thread. A new chat thread begins at each phase, seeded by the current snapshot.
	•	Checkpoint = rhythm. Every checkpoint gets its own commit, its own agent run, and a short summary added to the Bible.

⸻

🧩 2. File Structure

docs/
  CSC_BIBLE.md          ← long-form narrative, one chapter per phase
  CSC_SNAPSHOT.yaml     ← machine-readable current state
  PHASE_CHECKLIST.md    ← template filled per checkpoint
  DEV_WORKFLOW.md       ← this file
baselines/
  phase0/…              ← test artifacts


⸻

⚙️ 3. Phase Anatomy

Each phase has a clear theme and a bounded scope (e.g., “Phase 2 — Single-Source Modules”).

Step	Responsibility	Output
1	Brief (Rey → Nova)	Goals, guardrails, files to edit
2	Design sync (chat)	Finalized plan, no code yet
3	Agent run	File edits, tests, artifacts
4	Review (chat)	Diff summary, verification
5	Snapshot update	CSC_SNAPSHOT.yaml refreshed
6	Bible chapter	CSC_BIBLE.md gains one new section


⸻

🧱 4. Checkpoint Routine

Each checkpoint has its own PHASE_CHECKLIST.md copy filled out before work begins.
	1.	Pre-flight
	•	Tests green
	•	Snapshot loaded
	•	Known issues reviewed
	2.	Agent run (one per checkpoint)
	•	Perform all edits and tests atomically
	3.	Review & Diff
	•	Summarize deltas in chat
	•	Verify outputs against baseline
	4.	Commit
	•	Message format: P<phase>C<checkpoint>: <short title>
	5.	Update snapshot & Bible
	•	Increment checkpoint number
	•	Record decisions and notes

⸻

🧠 5. Handoff Protocol

When threads reset or a new phase begins:
	1.	Start with a Handoff Brief:
	•	Attach CSC_SNAPSHOT.yaml and CSC_BIBLE.md.
	•	List next checkpoint’s intent.
	2.	New thread reads both → immediate context restore.
	3.	Optional quick repo scan if structural drift occurred.

This turns the first five messages of every new thread into instant orientation instead of re-sync chatter.

⸻

🛠️ 6. Agent-Use Policy
	•	Frequency: one run per checkpoint, optional run at phase close.
	•	Scope: mechanical work only — file edits, tests, CI tweaks, baseline exports.
	•	Safety: never combine semantic design changes and mechanical refactors in the same run.
	•	Post-run ritual: update snapshot, summarize deltas, commit, tag.

⸻

🪶 7. CSC Bible Chapters

At the end of every phase, add a new section to CSC_BIBLE.md:

## Phase 2 — Single-Source Modules
**Date:** 2025-10-22  
**Objective:** merge *_rt.py variants → canonical modules  
**Highlights:**  
- Merged `legalize_rt.py` → `legalize.py`  
- Deleted `events_std.py`, `materialize.py`  
- Added import shims w/ deprecation warnings  
**Tests:** all green  
**Snapshot Tag:** v0.29.0-phase2-baseline  
**Notes:** no functional change, CI verified.

This keeps a human narrative of progress — the part no automation can replace.

⸻

🔐 8. Commit & Tag Convention

P<phase>C<checkpoint>: <title>
example: P0C3: Capture baseline artifacts

End-of-phase tags:

v0.<minor>.0-phase<phase>-baseline


⸻

🪜 9. Rollback Safety
	•	Each checkpoint commit is atomic and reversible.
	•	Baselines stored under /baselines/phaseX/ allow artifact diffing.
	•	CI remains the arbiter: green before and after every commit.

⸻

🪶 10. Living Documents

After every checkpoint:
	•	CSC_SNAPSHOT.yaml → updated automatically by Nova (or manually if no Agent).
	•	CSC_BIBLE.md → one-paragraph narrative append.
	•	DEV_WORKFLOW.md → rarely changes; acts as constitution.

⸻

🌙 11. Future Expansion

When CrapsSim-Evo integration begins:
	•	Add an “EVO_SYNC” flag in the snapshot.
	•	Bible gains a second volume (EVO_BIBLE.md).
	•	Workflow pattern remains identical.

⸻

End of File
(Keep this file concise, human-legible, and in version control. It’s our handshake when time or memory resets.)

⸻