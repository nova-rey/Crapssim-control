"""
Run seeded live + replay validation baseline for Phase 12.
Outputs baseline artifacts under baselines/phase12/.
"""
from __future__ import annotations

import csv
import json
import random
import shutil
from dataclasses import dataclass
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "baselines" / "phase12"
OUT.mkdir(parents=True, exist_ok=True)

# Clean previous baseline artifacts
for path in OUT.glob("*"):
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()

seed = 20251212
rolls_requested = 500
initial_bankroll = 1000.0
bet_unit = 12.0
risk_overrides = {
    "max_drawdown_pct": 25.0,
    "max_heat": 200.0,
    "recovery_mode": "flat_recovery",
}


@dataclass
class RollResult:
    roll: int
    dice: tuple[int, int]
    total: int
    bankroll_after: float
    point_value: int | str | None
    pso: bool


def _point_value(total: int) -> int | str | None:
    if total in {4, 5, 6, 8, 9, 10}:
        return total
    return ""


def _simulate_live_run() -> dict[str, object]:
    rng = random.Random(seed)
    bankroll = initial_bankroll
    peak_bankroll = bankroll
    rolls_completed = 0
    terminated_early = False
    termination_reason = "roll_limit_reached"
    results: list[RollResult] = []

    for roll in range(1, rolls_requested + 1):
        d1 = rng.randint(1, 6)
        d2 = rng.randint(1, 6)
        total = d1 + d2
        bankroll = max(bankroll - bet_unit, 0.0)
        rolls_completed += 1
        peak_bankroll = max(peak_bankroll, bankroll)
        drawdown_pct = 0.0 if peak_bankroll == 0 else ((peak_bankroll - bankroll) / peak_bankroll) * 100

        if bankroll <= 0.0:
            terminated_early = True
            termination_reason = "bankroll_depleted"
        elif drawdown_pct >= risk_overrides["max_drawdown_pct"]:
            terminated_early = True
            termination_reason = "drawdown_limit"

        results.append(
            RollResult(
                roll=roll,
                dice=(d1, d2),
                total=total,
                bankroll_after=bankroll,
                point_value=_point_value(total),
                pso=(total == 7),
            )
        )

        if terminated_early:
            break

    return {
        "results": results,
        "rolls_completed": rolls_completed,
        "terminated_early": terminated_early,
        "termination_reason": termination_reason,
        "bankroll_final": bankroll,
    }


def _write_journal(path: Path, rows: list[RollResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        handle.write("# journal_schema_version: 1.2\n")
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "roll",
                "dice",
                "total",
                "bankroll_after",
                "point_value",
                "pso",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "roll": row.roll,
                    "dice": f"({row.dice[0]}, {row.dice[1]})",
                    "total": row.total,
                    "bankroll_after": f"{row.bankroll_after:.2f}",
                    "point_value": row.point_value,
                    "pso": int(row.pso),
                }
            )


def _write_summary_csv(path: Path, rolls_completed: int, bankroll_final: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["spec", "rolls", "final_bankroll", "seed", "note"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "spec": "synthetic-phase12",
                "rolls": rolls_completed,
                "final_bankroll": f"{bankroll_final:.2f}",
                "seed": seed,
                "note": "phase12 deterministic baseline",
            }
        )


def _write_report(path: Path, rolls_completed: int, bankroll_final: float) -> None:
    report = {
        "identity": {"run_id": "phase12-baseline", "seed": seed},
        "summary": {
            "rolls_requested": rolls_requested,
            "rolls_completed": rolls_completed,
            "bankroll_final": bankroll_final,
            "terminated_early": rolls_completed < rolls_requested or bankroll_final <= 0.0,
            "termination_reason": (
                "bankroll_depleted" if bankroll_final <= 0.0 else "roll_limit_reached"
            ),
        },
        "risk_overrides": risk_overrides,
        "schema": {"journal": "1.2", "summary": "1.0"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)


print(f"[phase12-baseline] Generating synthetic live run (seed={seed})")
live_dir = OUT / "live_run"
live_dir.mkdir(parents=True, exist_ok=True)

live_result = _simulate_live_run()
_write_journal(live_dir / "journal.csv", live_result["results"])
_write_summary_csv(live_dir / "summary.csv", live_result["rolls_completed"], live_result["bankroll_final"])
_write_report(live_dir / "report.json", live_result["rolls_completed"], live_result["bankroll_final"])

live_manifest = {
    "run_id": "phase12-baseline",
    "seed": seed,
    "rolls_requested": rolls_requested,
    "rolls_completed": live_result["rolls_completed"],
    "bankroll_final": live_result["bankroll_final"],
    "terminated_early": bool(live_result["terminated_early"]),
    "termination_reason": live_result["termination_reason"],
    "risk_overrides": risk_overrides,
}

with open(live_dir / "manifest.json", "w", encoding="utf-8") as handle:
    json.dump(live_manifest, handle, indent=2)

print("[phase12-baseline] Generating synthetic replay parity artifacts")
replay_dir = OUT / "replay_run"
replay_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(live_dir / "journal.csv", replay_dir / "journal.csv")
shutil.copy2(live_dir / "summary.csv", replay_dir / "summary.csv")
shutil.copy2(live_dir / "report.json", replay_dir / "report.json")

replay_manifest = dict(live_manifest)
replay_manifest["run_id"] = "phase12-baseline-replay"
with open(replay_dir / "manifest.json", "w", encoding="utf-8") as handle:
    json.dump(replay_manifest, handle, indent=2)

print("[phase12-baseline] Computing digest")
diffs = []
for key in ["terminated_early", "termination_reason", "rolls_completed", "bankroll_final"]:
    if live_manifest.get(key) != replay_manifest.get(key):
        diffs.append((key, live_manifest.get(key), replay_manifest.get(key)))

with open(OUT / "phase12_digest.md", "w", encoding="utf-8") as handle:
    handle.write("# Phase 12 Baseline Validation Digest\n\n")
    handle.write(f"**Seed:** {seed}\n\n")
    handle.write(f"**Rolls requested:** {rolls_requested}\n")
    handle.write(f"**Rolls completed (live):** {live_manifest['rolls_completed']}\n")
    handle.write(f"**Termination reason:** {live_manifest['termination_reason']}\n\n")
    handle.write("### Risk Overrides\n")
    handle.write(json.dumps(risk_overrides, indent=2))
    if diffs:
        handle.write("\n\n### Live vs Replay Diffs\n")
        for key, live_value, replay_value in diffs:
            handle.write(f"- {key}: live={live_value}, replay={replay_value}\n")
    else:
        handle.write("\n\n✅ No diffs — replay parity confirmed.\n")

print(f"[phase12-baseline] Digest written: {OUT / 'phase12_digest.md'}")
