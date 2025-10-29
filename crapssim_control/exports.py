"""
exports.py -- Batch 11
Lightweight CSV/JSON exporters for Crapssim-Control.

Public functions:
  - export_session_json(tracker, path)
  - export_ledger_csv(tracker, path)
  - export_intents_csv(tracker, path)
  - export_bet_attrib_csv(tracker, path)
  - export_histograms_csv(tracker, path)

Design notes:
  - Uses the public Tracker snapshot() + attached shims (ledger, bet_attrib, histograms).
  - Does NOT mutate gameplay or require external deps; pure stdlib.
  - CSVs are wide enough to be analysis-ready without overfitting to any BI tool.
"""

from __future__ import annotations

import csv
import json
from typing import Any, Dict, Iterable, List


# -----------------------------
# Utilities
# -----------------------------


def _ensure_snapshot(tracker: Any) -> Dict[str, Any]:
    if not hasattr(tracker, "snapshot"):
        raise TypeError("tracker has no snapshot()")
    snap = tracker.snapshot()
    if not isinstance(snap, dict):
        raise TypeError("snapshot() must return a dict")
    return snap


def _write_csv(path: str, rows: Iterable[Dict[str, Any]], fieldnames: List[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _flatten_meta(meta: Any) -> str:
    """Return a JSON string for arbitrary meta dicts; keeps CSV schema stable."""
    try:
        return json.dumps(meta, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return ""


# -----------------------------
# Exports
# -----------------------------


def export_session_json(tracker: Any, path: str) -> None:
    """
    Dump the current tracker snapshot to a single JSON file.

    This includes (if enabled/wired): ledger, bet_attrib, history (hand/shooter/session hits), etc.
    """
    snap = _ensure_snapshot(tracker)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)


def export_ledger_csv(tracker: Any, path: str) -> None:
    """
    Export ledger entries (open + closed) as rows.

    Columns:
      id, status, bet, canon_bet_type, category, amount, payout, result, realized_pnl,
      created_ts, closed_ts, meta_json
    """
    snap = _ensure_snapshot(tracker)
    ledger = snap.get("ledger") or {}
    open_rows = ledger.get("open") or []
    closed_rows = ledger.get("closed") or []

    rows: List[Dict[str, Any]] = []
    for src in (open_rows, closed_rows):
        for e in src:
            meta = e.get("meta") or {}
            rows.append(
                {
                    "id": e.get("id"),
                    "status": e.get("status"),
                    "bet": e.get("bet"),
                    "canon_bet_type": meta.get("canon_bet_type"),
                    "category": e.get("category"),
                    "amount": e.get("amount"),
                    "payout": e.get("payout"),
                    "result": e.get("result"),
                    "realized_pnl": e.get("realized_pnl"),
                    "created_ts": e.get("created_ts"),
                    "closed_ts": e.get("closed_ts"),
                    "meta_json": _flatten_meta(meta),
                }
            )

    _write_csv(
        path,
        rows,
        fieldnames=[
            "id",
            "status",
            "bet",
            "canon_bet_type",
            "category",
            "amount",
            "payout",
            "result",
            "realized_pnl",
            "created_ts",
            "closed_ts",
            "meta_json",
        ],
    )


def export_intents_csv(tracker: Any, path: str) -> None:
    """
    Export intents (open/matched/canceled) as rows.

    Columns:
      id, status, bet, number, stake, reason, matched_entry_id,
      created_ts, matched_ts, canceled_ts, created_roll_index, meta_json
    """
    snap = _ensure_snapshot(tracker)
    intents = (snap.get("ledger") or {}).get("intents") or {}

    rows: List[Dict[str, Any]] = []
    for bucket in ("open", "matched", "canceled"):
        for i in intents.get(bucket, []) or []:
            meta = i.get("meta") or {}
            rows.append(
                {
                    "id": i.get("id"),
                    "status": i.get("status"),
                    "bet": i.get("bet"),
                    "number": i.get("number"),
                    "stake": i.get("stake"),
                    "reason": i.get("reason"),
                    "matched_entry_id": i.get("matched_entry_id"),
                    "created_ts": i.get("created_ts"),
                    "matched_ts": i.get("matched_ts"),
                    "canceled_ts": i.get("canceled_ts"),
                    "created_roll_index": i.get("created_roll_index"),
                    "meta_json": _flatten_meta(meta),
                }
            )

    _write_csv(
        path,
        rows,
        fieldnames=[
            "id",
            "status",
            "bet",
            "number",
            "stake",
            "reason",
            "matched_entry_id",
            "created_ts",
            "matched_ts",
            "canceled_ts",
            "created_roll_index",
            "meta_json",
        ],
    )


def export_bet_attrib_csv(tracker: Any, path: str) -> None:
    """
    Export per-bet-type attribution metrics (Batch 5/7/10) as one row per canonical bet type.

    Columns:
      bet_type, placed_count, resolved_count, push_count,
      total_staked, exposure_rolls, peak_open_bets,
      wins, losses, pnl, total_commission,
      hit_rate, roi, pnl_per_exposure_roll,
      comeout_resolved, point_resolved
    """
    snap = _ensure_snapshot(tracker)
    by_type = ((snap.get("bet_attrib") or {}).get("by_bet_type")) or {}

    rows: List[Dict[str, Any]] = []
    for bet_type, stats in by_type.items():
        ctx = (stats or {}).get("_ctx") or {}
        rows.append(
            {
                "bet_type": bet_type,
                "placed_count": stats.get("placed_count", 0),
                "resolved_count": stats.get("resolved_count", 0),
                "push_count": stats.get("push_count", 0),
                "total_staked": stats.get("total_staked", 0.0),
                "exposure_rolls": stats.get("exposure_rolls", 0),
                "peak_open_bets": stats.get("peak_open_bets", 0),
                "wins": stats.get("wins", 0),
                "losses": stats.get("losses", 0),
                "pnl": stats.get("pnl", 0.0),
                "total_commission": stats.get("total_commission", 0.0),
                "hit_rate": stats.get("hit_rate", 0.0),
                "roi": stats.get("roi", 0.0),
                "pnl_per_exposure_roll": stats.get("pnl_per_exposure_roll", 0.0),
                "comeout_resolved": ctx.get("comeout_resolved", 0),
                "point_resolved": ctx.get("point_resolved", 0),
            }
        )

    _write_csv(
        path,
        rows,
        fieldnames=[
            "bet_type",
            "placed_count",
            "resolved_count",
            "push_count",
            "total_staked",
            "exposure_rolls",
            "peak_open_bets",
            "wins",
            "losses",
            "pnl",
            "total_commission",
            "hit_rate",
            "roi",
            "pnl_per_exposure_roll",
            "comeout_resolved",
            "point_resolved",
        ],
    )


def export_histograms_csv(tracker: Any, path: str) -> None:
    """
    Export hand/shooter/session histograms as columns in a single CSV row.

    Columns:
      scope, h2..h12 (counts for totals 2..12), inside_hits, outside_hits
      (scope ∈ {"hand","shooter","session"})
    """
    snap = _ensure_snapshot(tracker)
    hist = snap.get("history") or {}

    def row_from(scope: str, counts: Dict[str, Any], inside: int, outside: int) -> Dict[str, Any]:
        row = {"scope": scope, "inside_hits": inside, "outside_hits": outside}
        for n in range(2, 13):
            row[f"h{n}"] = int(counts.get(str(n), 0))
        return row

    rows: List[Dict[str, Any]] = []
    rows.append(
        row_from(
            "hand",
            hist.get("hand_hits", {}),
            int(hist.get("hand_inside_hits", 0)),
            int(hist.get("hand_outside_hits", 0)),
        )
    )
    rows.append(
        row_from(
            "shooter",
            hist.get("shooter_hits", {}),
            int(hist.get("shooter_inside_hits", 0)),
            int(hist.get("shooter_outside_hits", 0)),
        )
    )
    rows.append(
        row_from(
            "session",
            hist.get("session_hits", {}),
            # no explicit inside/outside for session in Batch 8; leave as zeros
            0,
            0,
        )
    )

    fieldnames = ["scope"] + [f"h{n}" for n in range(2, 13)] + ["inside_hits", "outside_hits"]
    _write_csv(path, rows, fieldnames=fieldnames)
