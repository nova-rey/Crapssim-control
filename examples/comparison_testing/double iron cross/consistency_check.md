# Consistency Check: Vanilla CrapsSim vs Crapssim-Control (CSC)

## Purpose
This test ensures that **Crapssim-Control (CSC)** produces results consistent with the original **CrapsSim vanilla strategies** when run with the same seed, rolls, and table settings.

By comparing a known strategy (`IronCross`) in both formats:

- **Vanilla Python Strategy** (`run_ironcross_vanilla.py`)
- **CSC JSON Spec** (`iron_cross_csc.json`)

…we can confirm that the dice sequences, bet handling, and final bankrolls stay aligned.  
Any mismatches highlight event-timing differences (e.g., when Field bets get posted), which helps validate and refine CSC.

—

## Files
- `examples/run_ironcross_vanilla.py`  
  Runs CrapsSim’s built-in `IronCross` strategy directly in Python.

- `specs/iron_cross_csc.json`  
  Equivalent strategy expressed as a CSC spec.

—

## How to Run

### 1. Run the Vanilla Strategy
```bash
python examples/run_ironcross_vanilla.py —rolls 200 —seed 42

This prints a result line like:

RESULT: rolls=200 bankroll=1015.00

2. Run the CSC Spec

crapssim-ctl run specs/iron_cross_csc.json —rolls 200 —seed 42

This prints a similar result:

RESULT: rolls=200 bankroll=1015.00


⸻

Expected Outcome
	•	Both runs should produce nearly identical bankrolls when seeded the same.
	•	Minor mismatches may occur if bet timing (e.g., Field bets) differs between engines.
	•	If bankrolls diverge, check which per-roll event CSC should hook into (pre_roll, roll, or dice_rolled) and adjust the JSON spec accordingly.

⸻

Why This Matters

This test is a litmus test:
	•	Confirms CSC matches CrapsSim’s expected strategy behavior.
	•	Proves that CSC specs are trustworthy when migrating from Python scripts to JSON.
	•	Builds confidence before evolving more complex strategies.

⸻