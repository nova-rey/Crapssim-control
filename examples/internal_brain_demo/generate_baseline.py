#!/usr/bin/env python3
"""Generate Phase 5 baseline artifacts for the internal brain demo."""
from __future__ import annotations

import json
from datetime import datetime, UTC
import csv
from pathlib import Path
import platform
import sys
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crapssim_control.spec_loader import load_spec_file
from crapssim_control.controller import ControlStrategy
from crapssim_control.rules_engine.evaluator import evaluate_rules
from crapssim_control.rules_engine.actions import ACTIONS, is_legal_timing
from crapssim_control.rules_engine.journal import DecisionJournal
from crapssim_control.schemas import JOURNAL_SCHEMA_VERSION, SUMMARY_SCHEMA_VERSION
from crapssim_control.spec_validation import VALIDATION_ENGINE_VERSION

BASELINE_DIR = Path("baselines/phase5")
SPEC_PATH = Path("examples/internal_brain_demo/spec.yaml")
RUN_ID = "phase5-ittt-demo"
SEED = 12345

EVENT_SEQUENCE: List[Dict[str, int | float | bool]] = [
    {"hand_id": 1, "roll_in_hand": 1, "point_on": False, "bankroll_after": 940, "box_hits": 2, "last_roll_total": 6},
    {"hand_id": 1, "roll_in_hand": 2, "point_on": False, "bankroll_after": 930, "box_hits": 1, "last_roll_total": 5},
    {"hand_id": 2, "roll_in_hand": 1, "point_on": True, "bankroll_after": 920, "box_hits": 2, "last_roll_total": 4},
    {"hand_id": 2, "roll_in_hand": 2, "point_on": True, "bankroll_after": 880, "box_hits": 2, "last_roll_total": 8},
    {"hand_id": 3, "roll_in_hand": 1, "point_on": False, "bankroll_after": 960, "box_hits": 0, "last_roll_total": 10},
    {"hand_id": 3, "roll_in_hand": 2, "point_on": False, "bankroll_after": 940, "box_hits": 2, "last_roll_total": 9},
]


def main() -> None:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)

    spec, deprecations = load_spec_file(SPEC_PATH)
    controller = ControlStrategy(spec, spec_deprecations=deprecations, spec_path=SPEC_PATH)
    ruleset = getattr(controller, "ruleset", [])

    journal_path = BASELINE_DIR / "decision_journal.jsonl"
    if journal_path.exists():
        journal_path.unlink()
    journal = DecisionJournal(str(journal_path))
    controller.journal = journal

    hand_scoped_rules = {
        str(rule.get("id"))
        for rule in ruleset
        if isinstance(rule, dict) and str(rule.get("scope", "")).lower() == "hand"
    }

    peak_bankroll = 1000.0
    executed_actions = 0
    total_records = 0
    prev_hand = None
    roll_summaries: List[Dict[str, object]] = []

    for index, event in enumerate(EVENT_SEQUENCE, start=1):
        journal.tick()
        hand_id = int(event["hand_id"])
        if prev_hand is not None and hand_id != prev_hand:
            for rid in hand_scoped_rules:
                journal.scope_flags.discard(rid)
        prev_hand = hand_id

        bankroll_after = float(event["bankroll_after"])
        peak_bankroll = max(peak_bankroll, bankroll_after)
        drawdown_after = peak_bankroll - bankroll_after

        context = {
            "bankroll_after": bankroll_after,
            "drawdown_after": drawdown_after,
            "hand_id": hand_id,
            "roll_in_hand": int(event["roll_in_hand"]),
            "point_on": bool(event["point_on"]),
            "box_hits": event.get("box_hits", 0),
            "last_roll_total": event.get("last_roll_total"),
        }

        decisions = evaluate_rules(ruleset, context)
        rule_lookup = {str(rule.get("id")): rule for rule in ruleset if isinstance(rule, dict)}
        verbs_executed: set[str] = set()

        for decision in decisions:
            rule_id = str(decision.get("rule_id"))
            rule_def = rule_lookup.get(rule_id)
            if rule_def is None:
                continue

            action_text = str(rule_def.get("action", ""))
            scope = str(rule_def.get("scope", "roll"))
            cooldown_raw = rule_def.get("cooldown", 0)
            try:
                cooldown = int(cooldown_raw)
            except (TypeError, ValueError):
                cooldown = 0

            decision.update(
                {
                    "action": action_text,
                    "scope": scope,
                    "cooldown": cooldown,
                    "run_id": RUN_ID,
                    "origin": f"rule:{rule_id}",
                    "hand_id": hand_id,
                    "roll_in_hand": context["roll_in_hand"],
                    "point_on": context["point_on"],
                }
            )
            for extra_key in ("profile", "target", "pattern"):
                if extra_key in rule_def and extra_key not in decision:
                    decision[extra_key] = rule_def[extra_key]

            decision["cooldown_remaining"] = journal.cooldowns.get(rule_id, 0)
            allowed, reason = journal.can_fire(rule_id, scope, cooldown)
            decision["cooldown_allowed"] = allowed
            decision["cooldown_reason"] = reason

            verb = action_text.split("(")[0]
            legal, timing_reason = is_legal_timing(
                {"resolving": False, "point_on": context["point_on"], "roll_in_hand": context["roll_in_hand"]},
                {"verb": verb},
            )
            decision["timing_legal"] = legal
            decision["timing_reason"] = timing_reason

            duplicate_blocked = verb in verbs_executed
            decision["duplicate_blocked"] = duplicate_blocked

            executed = False
            result_payload = None

            if decision.get("fired") and allowed and legal and not duplicate_blocked:
                action = ACTIONS.get(verb)
                if action is not None:
                    result_payload = action.execute({"context": context}, decision)
                    executed = True
                    verbs_executed.add(verb)
                    journal.apply_fire(rule_id, scope, cooldown)
                    decision["cooldown_remaining"] = journal.cooldowns.get(rule_id, 0)

            if executed:
                executed_actions += 1
                decision["executed"] = True
                decision["result"] = result_payload
            else:
                decision["executed"] = False
                if duplicate_blocked:
                    decision["note"] = "duplicate_blocked"
                elif not allowed:
                    decision["note"] = reason
                elif not legal:
                    decision["note"] = timing_reason

            journal.record(decision)
            total_records += 1

        roll_summaries.append({"index": index, "context": context, "decisions": decisions})

    journal_csv = BASELINE_DIR / "journal.csv"
    records = [json.loads(line) for line in journal_path.read_text(encoding="utf-8").splitlines()]
    fieldnames = sorted({key for record in records for key in record.keys()})
    with journal_csv.open("w", newline="", encoding="utf-8") as dest:
        writer = csv.DictWriter(dest, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record)

    report_path = BASELINE_DIR / "report.json"
    engine_version = getattr(controller, "engine_version", "unknown")
    run_flag_values = {
        "demo_fallbacks": False,
        "strict": False,
        "embed_analytics": True,
    }
    run_flag_sources = {
        "demo_fallbacks": "default",
        "strict": "default",
        "embed_analytics": "default",
        "export": "default",
        "webhook_enabled": "default",
        "evo_enabled": "default",
        "trial_tag": "default",
    }
    report = {
        "run_id": RUN_ID,
        "seed": SEED,
        "manifest_path": str(BASELINE_DIR / "manifest.json"),
        "journal_schema_version": JOURNAL_SCHEMA_VERSION,
        "summary_schema_version": SUMMARY_SCHEMA_VERSION,
        "journal": str(journal_path),
        "csv": str(journal_csv),
        "records": total_records,
        "executed_actions": executed_actions,
        "events_simulated": len(EVENT_SEQUENCE),
        "rules": [str(rule.get("id")) for rule in ruleset if isinstance(rule, dict)],
        "timing_enforced": True,
        "metadata": {
            "demo_fallbacks_default": False,
            "validation_engine": VALIDATION_ENGINE_VERSION,
            "run_flags": {
                "values": run_flag_values,
                "sources": run_flag_sources,
                "webhook_enabled": False,
                "webhook_url_source": "default",
                "webhook_url_masked": False,
                "strict_source": "default",
                "demo_fallbacks_source": "default",
                "embed_analytics_source": "default",
                "export_source": "default",
                "webhook_enabled_source": "default",
                "evo_enabled_source": "default",
                "trial_tag_source": "default",
            },
        },
    }
    report["metadata"]["engine"] = {
        "name": "CrapsSim-Control",
        "version": engine_version,
        "python": platform.python_version(),
    }
    report["metadata"]["artifacts"] = {
        "journal": str(journal_path),
        "report": str(report_path),
        "manifest": str(BASELINE_DIR / "manifest.json"),
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    manifest_path = BASELINE_DIR / "manifest.json"
    manifest = {
        "run_id": RUN_ID,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "seed": SEED,
        "spec": str(SPEC_PATH),
        "artifacts": {
            "decision_journal": str(journal_path),
            "journal_csv": str(journal_csv),
            "report": str(report_path),
        },
        "events": roll_summaries,
    }
    manifest["schema"] = {
        "journal": JOURNAL_SCHEMA_VERSION,
        "summary": SUMMARY_SCHEMA_VERSION,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
