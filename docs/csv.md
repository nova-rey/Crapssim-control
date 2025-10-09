# CSV Journal and Summary System

_Last updated: Phase 3 Checkpoint 8_

The CrapsSim-Control CSV subsystem provides a **transparent event-level journal** of all simulation actions, along with **summarization tools** for quick analysis or downstream visualization.

---

## 📘 Overview

When enabled via the spec file (`run.csv.enabled: true`), every simulation automatically records a journal in CSV format.  
Each row represents one **action envelope** emitted by either a **template** or a **rule** during the run.

The resulting file is both human-readable and easily consumed by tools such as pandas, Excel, or visualization dashboards.

---

## 🧩 Journal Schema

Each journal row contains the following stable columns (locked in P3C7):

| Column | Type | Description |
|--------|------|-------------|
| `ts` | ISO-8601 UTC string | Timestamp when the action was written |
| `run_id` | string | Run identifier for grouping |
| `seed` | int/string | RNG seed for reproducibility |
| `event_type` | string | Context event (`point_established`, `roll`, etc.) |
| `point` | int/str | Active point value (if any) |
| `rolls_since_point` | int | Counter of rolls since point establishment |
| `on_comeout` | bool | True if current roll is on come-out |
| `mode` | string | Current mode name (`Main`, `Recovery`, etc.) |
| `units` | float | Current base unit size |
| `bankroll` | float | Snapshot bankroll |
| `source` | string | Origin of the action (`template` or `rule`) |
| `id` | string | Stable producer identifier (`template:Main`, `rule:auto_press_6`, …) |
| `action` | string | Action verb (`set`, `press`, `reduce`, `clear`, `switch_mode`) |
| `bet_type` | string | Canonical bet key (`place_6`, `odds_8_pass`, etc.) |
| `amount` | float | Numeric amount for applicable actions |
| `notes` | string | Free-form context or comment |
| `extra` | JSON string | Optional forward-compatibility payload |

---

## 🧪 Example (Quickstart)

Example file: `examples/quickstart_spec.json`

```json
{
  "name": "Quickstart – Place 6/8 with Pass",
  "run": {
    "rolls": 60,
    "seed": 1234,
    "csv": {
      "enabled": true,
      "path": "journal.csv",
      "append": false,
      "run_id": "quickstart"
    }
  }
}

Running the simulation:

python -m crapssim_control.cli run examples/quickstart_spec.json

produces journal.csv, then you can summarize it:

python -m crapssim_control.cli journal summarize journal.csv --out summary.csv


⸻

📊 Summary Schema

Each summary row (per run ID or per file) contains:

Column	Description
run_id	Group key (or file-based fallback)
rows_total	Total journal rows
actions_total	Usually identical to rows_total
sets, clears, presses, reduces, switch_mode	Counts per action type
unique_bets, modes_used, points_seen	Distinct counts
roll_events, regress_events	Event counters
sum_amount_set, sum_amount_press, sum_amount_reduce	Numeric totals
first_timestamp, last_timestamp	Time window (ISO-8601)
path	Source CSV path


⸻

⚙️ Programmatic API

From Python:

from crapssim_control.csv_summary import summarize_journal, write_summary_csv

summaries = summarize_journal("journal.csv")
write_summary_csv(summaries, "summary.csv")


⸻

🧱 Developer Notes
	•	The journal writer (CSVJournal) automatically adds headers if missing.
	•	run_id and seed are injected per-row for traceability.
	•	Boolean and numeric fields are serialized as strings for CSV safety.
	•	All time values use UTC for consistency.
	•	CSV output is append-safe; use append=False to overwrite runs.
	•	The subsystem is engine-agnostic — usable with any compliant action stream.

⸻

✅ Validation & Testing

Tests in tests/test_csv_roundtrip_example.py and tests/test_examples_validate.py confirm:
	•	Correct header layout and round-trip consistency.
	•	Valid spec example (quickstart_spec.json).
	•	Proper CLI and API operation without an engine dependency.

⸻

🚀 Future Work
	•	Optional “cover-sheet only” summary mode.
	•	Multi-run aggregation (e.g. per strategy across seeds).
	•	Pandas helper utilities for analytics notebooks.

⸻

This document is part of CrapsSim-Control Phase 3 CSV Journal expansion.