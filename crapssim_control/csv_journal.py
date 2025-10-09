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


@dataclass
class CSVJournal:
    """
    Append-friendly CSV logger for Action Envelopes.

    One CSV row per envelope, enriched with a lightweight snapshot so downstream
    analysis can pivot by event/point/mode without joining files.

    Columns (stable; locked for tests):
        ts, run_id, seed,
        event_type, point, rolls_since_point, on_comeout,
        mode, units, bankroll,
        source, id, action, bet_type, amount, notes,
        extra
    """

    path: str | os.PathLike[str]
    append: bool = True
    # Optional run-scoped metadata (recorded per-row for simplicity)
    run_id: Optional[str] = None
    seed: Optional[int] = None

    # Column order MUST match tests
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
            # If we can't stat for some reason, assume it has a header already
            return False

    def ensure_header(self) -> None:
        """Explicit header write (idempotent if file already has content)."""
        self._ensure_parent()
        if not self._needs_header():
            return
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._columns, extrasaction="ignore")
            writer.writeheader()

    # ---- Public API ---------------------------------------------------------

    def write_actions(self, actions: Iterable[Dict[str, Any]], snapshot: Dict[str, Any] | None = None) -> int:
        """
        Append one row per action envelope with selected snapshot fields.

        Parameters
        ----------
        actions : iterable of action envelopes (dicts)
            Must include the canonical keys: source, id, action, bet_type, amount, notes.
        snapshot : dict
            Context fields (event_type, point, rolls_since_point, on_comeout, mode, units, bankroll, extra?)

        Returns
        -------
        int : number of rows successfully written
        """
        acts = list(actions or [])
        if not acts:
            # No-op, but still ensure header if the file doesn't exist yet
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
            # Snapshot fields (defaults)
            event_type = _as_str(snap.get("event_type") or snap.get("type") or "")
            point = snap.get("point")
            rolls_since_point = snap.get("rolls_since_point")
            on_comeout = snap.get("on_comeout")
            mode_val = _as_str(snap.get("mode"))
            units = _coerce_num(snap.get("units"))
            bankroll = _coerce_num(snap.get("bankroll"))
            extra = snap.get("extra")  # Can be any JSON-serializable

            rows_written = 0
            for a in acts:
                # Envelope fields with defensive coercions
                src = _as_str(a.get("source"))
                aid = _as_str(a.get("id"))
                action = _as_str(a.get("action"))
                bet_type = _as_str(a.get("bet_type"))
                amount = _coerce_num(a.get("amount"))
                notes = _as_str(a.get("notes"))

                # Coercions for numeric-ish snapshot fields to keep tests happy
                def _as_int_or_blank(v: Any) -> str:
                    if isinstance(v, bool):
                        return ""  # never treat booleans as ints here
                    n = _coerce_num(v)
                    return "" if n is None else str(int(n))

                row = {
                    "ts": _iso_now(),
                    "run_id": _as_str(self.run_id),
                    "seed": _as_str(self.seed) if self.seed is not None else "",
                    "event_type": event_type,
                    "point": _as_int_or_blank(point),
                    "rolls_since_point": _as_int_or_blank(rolls_since_point),
                    "on_comeout": str(bool(on_comeout)) if on_comeout is not None else "",
                    "mode": mode_val,
                    "units": "" if units is None else str(units),
                    "bankroll": "" if bankroll is None else str(bankroll),
                    "source": src,
                    "id": aid,
                    "action": action,
                    "bet_type": bet_type,
                    "amount": "" if amount is None else str(amount),
                    "notes": notes,
                    "extra": _as_str(extra) if extra is not None else "",
                }

                try:
                    writer.writerow(row)
                    rows_written += 1
                except Exception:
                    # Best-effort: skip bad rows without crashing the run
                    continue

        return rows_written