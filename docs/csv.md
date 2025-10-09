⸻

CSV Journals & Summaries

CrapsSim-Control supports writing detailed per-action journals and high-level summaries of simulation runs.

⸻

1️⃣ Journal CSV (runtime log)

When journaling is enabled in the spec:

run:
  csv:
    enabled: true
    path: ./journals/latest.csv
    append: false

each triggered action (template or rule) produces a row in the CSV.

Column	Description
timestamp	ISO time of event
run_id	Unique ID for this simulation run
event_type	e.g. roll, point_established, etc.
mode	Active strategy mode
point	Current point (0 if come-out)
rolls_since_point	Counter of rolls since point established
on_comeout	True/False
source	"template" or "rule"
id	Action or rule identifier
action	"set", "press", "reduce", "clear", "switch_mode"
bet_type	Affected bet name
amount	Bet size (if applicable)

This file is the event log used for post-analysis.

⸻

2️⃣ Journal Summaries

Once a journal exists, you can summarize it directly from the CLI.

Basic usage

crapssim-ctl journal summarize journals/latest.csv

Prints a tab-separated table like:

run_id_or_file	rows_total	actions_total	sets	presses	reduces	clears	switch_mode	unique_bets	modes_used	points_seen	roll_events	t_first	t_last
run-001	        7	        7	            3	    1	    1	    2	    0	            3	        1	        1	        3	        2025-10-09T10:00:00	2025-10-09T10:00:15

Output to file

crapssim-ctl journal summarize journals/latest.csv --out summaries/summary.csv

Creates a summarized CSV with the following columns:

Column	Meaning
run_id_or_file	Run ID or fallback filename
rows_total	Total journaled rows
actions_total	Total actions (1:1 with rows)
sets / presses / reduces / clears / switch_mode	Action counts
unique_bets	Distinct bet types encountered
modes_used	Distinct strategy modes
points_seen	Distinct point numbers
roll_events	Unique roll timestamps
regress_events	Regressions triggered
sum_amount_set / sum_amount_press / sum_amount_reduce	Monetary totals by action type
t_first / t_last	First & last timestamps in the journal
path	Source CSV file path

Options

Flag	Description
--by-run-id	Group by run_id (default)
--by-file	Treat entire file as one group
--out <path>	Write summary CSV instead of printing
--append	Append to an existing summary file


⸻

3️⃣ Typical workflow
	1.	Run a strategy with journaling enabled.
	2.	Inspect the generated journals/ CSVs.
	3.	Summarize each file:

crapssim-ctl journal summarize journals/*.csv --out summaries/summary.csv --append


	4.	Analyze or visualize summaries/summary.csv in your preferred tool (Excel, pandas, etc.).

⸻

4️⃣ Example integration snippet

from crapssim_control.csv_summary import summarize_journal, write_summary_csv

summaries = summarize_journal("journals/latest.csv", group_by_run_id=True)
write_summary_csv(summaries, "summaries/summary.csv")


⸻