# crapssim_control/csv_journal.py
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _iso_now() -> str:
    # Always UTC to keep logs sortable/consistent across machines.
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _coerce_num(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    try:
        return float(str(x))
    except Exception:
        return None


def _as_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, (dict, list, tuple)):
        try:
            return json.dumps(x, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            return str(x)
    return str(x)


def _merge_extra(snapshot: Dict[str, Any], action: Dict[str, Any]) -> Any:
    """
    Build an 'extra' payload for the CSV row:
      - Start with snapshot.get("extra") (string/dict allowed)
      - Merge in canonical event hints: roll, event_point (when present)
      - Merge per-action seq (if present)
    Returns a string (JSON if dict-like) or passthrough string.
    """
    snap_extra = snapshot.get("extra")
    base: Dict[str, Any] = {}

    # If caller provided a dict-like extra, start with that
    if isinstance(snap_extra, dict):
        base.update(snap_extra)
    elif snap_extra is not None and str(snap_extra).strip() != "":
        # preserve non-dict extra under a conventional key
        base["extra"] = str(snap_extra)

    # Canonical event hints (if provided in snapshot by controller)
    roll_val = _coerce_num(snapshot.get("roll"))
    if roll_val is not None:
        base["roll"] = int(roll_val) if float(roll_val).is_integer() else roll_val

    evt_pt = snapshot.get("event_point")
    evt_pt_num = _coerce_num(evt_pt)
    if evt_pt_num is not None:
        base["event_point"] = int(evt_pt_num) if float(evt_pt_num).is_integer() else evt_pt_num

    # Per-action sequence (optional)
    if "seq" in action and action.get("seq") is not None:
        try:
            seq_num = int(action.get("seq"))
            base["seq"] = seq_num
        except Exception:
            base["seq"] = action.get("seq")

    # If base is still empty and original extra was a simple string, pass it through
    if not base and isinstance(snap_extra, str):
        return snap_extra

    return base if base else ""


@dataclass
class CSVJournal:
    """
    Append-friendly CSV logger for Action Envelopes.

    EXACT schema (locked):
      ts, run_id, seed,
      event_type, point, rolls_since_point, on_comeout,
      mode, units, bankroll,
      source, id, action, bet_type, amount, notes,
      extra

    Also supports a single-row "summary" record appended by write_summary(...):
      - event_type is set to "summary"
      - 'extra' holds a compact JSON summary object
    """

    path: str | os.PathLike[str]
    append: bool = True
    run_id: Optional[str] = None
    seed: Optional[int] = None

    _columns: List[str] = field(default_factory=lambda: [
        "ts", "run_id", "seed",
        "event_type", "point", "rolls_since_point", "on_comeout",
        "mode", "units", "bankroll",
        "source", "id", "action", "bet_type", "amount", "notes",
        "extra",
    ])

    def _ensure_parent(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def _needs_header(self) -> bool:
        p = Path(self.path)
        if not p.exists():
            return True
        try:
            return p.stat().st_size == 0
        except Exception:
            return False

    def ensure_header(self) -> None:
        self._ensure_parent()
        if not self._needs_header():
            return
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._columns, extrasaction="ignore")
            writer.writeheader()

    def write_actions(self, actions: Iterable[Dict[str, Any]], snapshot: Dict[str, Any] | None = None) -> int:
        acts = list(actions or [])
        if not acts:
            self.ensure_header()
            return 0

        self._ensure_parent()
        write_header = self._needs_header()
        mode_flag = "a" if self.append else "w"

        with open(self.path, mode_flag, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._columns, extrasaction="ignore")
            if write_header:
                writer.writeheader()

            snap = snapshot or {}

            event_type = _as_str(snap.get("event_type") or snap.get("type") or "")
            point = snap.get("point")
            rolls_since_point = snap.get("rolls_since_point")
            on_comeout = snap.get("on_comeout")
            mode_val = _as_str(snap.get("mode"))
            units = _coerce_num(snap.get("units"))
            bankroll = _coerce_num(snap.get("bankroll"))

            rows_written = 0
            for a in acts:
                src = _as_str(a.get("source"))
                aid = _as_str(a.get("id"))
                action = _as_str(a.get("action"))
                bet_type = _as_str(a.get("bet_type"))
                amount = _coerce_num(a.get("amount"))
                notes = _as_str(a.get("notes"))

                # Build enriched 'extra' payload (merges roll/event_point/seq)
                extra_payload = _merge_extra(snap, a)

                row = {
                    "ts": _iso_now(),
                    "run_id": _as_str(self.run_id),
                    "seed": _as_str(self.seed) if self.seed is not None else "",
                    "event_type": event_type,
                    "point": int(_coerce_num(point)) if _coerce_num(point) is not None else "",
                    "rolls_since_point": int(_coerce_num(rolls_since_point)) if _coerce_num(rolls_since_point) is not None else "",
                    "on_comeout": bool(on_comeout) if on_comeout is not None else "",
                    "mode": mode_val,
                    "units": units if units is not None else "",
                    "bankroll": bankroll if bankroll is not None else "",
                    "source": src,
                    "id": aid,
                    "action": action,
                    "bet_type": bet_type,
                    "amount": amount if amount is not None else "",
                    "notes": notes,
                    "extra": _as_str(extra_payload) if extra_payload is not None else "",
                }

                try:
                    writer.writerow(row)
                    rows_written += 1
                except Exception:
                    # Fail-open: skip problematic rows but keep file usable
                    continue

        return rows_written

    # ---------------- P5C1: summary writer ----------------

    def write_summary(self, summary: Dict[str, Any], snapshot: Dict[str, Any] | None = None) -> bool:
        """
        Append a single 'summary' row with the given summary dict in 'extra'.
        Returns True on success, False on failure. Never raises.
        """
        try:
            self._ensure_parent()
            write_header = self._needs_header()
            mode_flag = "a" if self.append else "w"
            with open(self.path, mode_flag, newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self._columns, extrasaction="ignore")
                if write_header:
                    writer.writeheader()

                snap = snapshot or {}
                row = {
                    "ts": _iso_now(),
                    "run_id": _as_str(self.run_id),
                    "seed": _as_str(self.seed) if self.seed is not None else "",
                    "event_type": "summary",
                    "point": "",
                    "rolls_since_point": "",
                    "on_comeout": "",
                    "mode": _as_str(snap.get("mode")),
                    "units": _coerce_num(snap.get("units")) or "",
                    "bankroll": _coerce_num(snap.get("bankroll")) or "",
                    "source": "system",
                    "id": "summary:run",  # <-- match test expectation
                    "action": "",
                    "bet_type": "",
                    "amount": "",
                    "notes": "",
                    "extra": _as_str(summary),
                }
                writer.writerow(row)
            return True
        except Exception:
            return False