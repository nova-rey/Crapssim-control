# crapssim_control/csv_journal.py
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, TextIO

from .schemas import JOURNAL_SCHEMA_VERSION


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
            return json.dumps(x, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
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


def write_roll_event(csv_writer, roll_summary: Dict[str, Any]):
    row = {
        "event_type": "roll_event",
        "roll_total": roll_summary.get("total"),
        "dice": roll_summary.get("dice"),
        "bankroll_after": roll_summary.get("snapshot", {}).get("bankroll_after"),
        "point_value": roll_summary.get("snapshot", {}).get("point_value"),
        "pso": roll_summary.get("pso"),
        "hand_id": roll_summary.get("snapshot", {}).get("hand_id"),
        "roll_in_hand": roll_summary.get("snapshot", {}).get("roll_in_hand"),
    }
    csv_writer.writerow(row)


def _write_csv_header(fh: TextIO, headers: List[str]) -> None:
    fh.write(f"# journal_schema_version: {JOURNAL_SCHEMA_VERSION}\n")
    fh.write(",".join(headers) + "\n")


def _append_adapter_snapshot_fields_if_enabled(
    controller: Any, row: Dict[str, Any], fieldnames: List[str]
) -> None:
    adapter = getattr(controller, "adapter", None)
    if not adapter:
        return
    try:
        from .engine_adapter import NullAdapter  # avoid top-level cycle
    except Exception:  # pragma: no cover - defensive
        NullAdapter = None  # type: ignore[assignment]
    if NullAdapter is not None and isinstance(adapter, NullAdapter):
        return
    snapshot_state = getattr(adapter, "snapshot_state", None)
    if not callable(snapshot_state):
        return
    try:
        snap = snapshot_state()
    except Exception:
        return
    if not isinstance(snap, dict):
        return
    for field in ("bankroll_after", "bet_6", "bet_8"):
        if field not in fieldnames:
            fieldnames.append(field)
    row["bankroll_after"] = snap.get("bankroll")
    bets_map = snap.get("bets")
    bets = bets_map if isinstance(bets_map, dict) else {}
    row["bet_6"] = bets.get("6", 0)
    row["bet_8"] = bets.get("8", 0)


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

    Semantics of `append`:
      - append=True  → always append
      - append=False → truncate on the *first* write of this run, then append thereafter

    P5C1/P5C2 compatibility retained. Convenience helpers added for P5C3/P5C4:
      - identity() returns {"run_id", "seed"}
      - path_str property exposes normalized CSV path
      - write_cover_sheet(...) writes a comment preamble (#-prefixed rows) only on new files
    """

    path: str | os.PathLike[str]
    append: bool = True
    run_id: Optional[str] = None
    seed: Optional[int] = None

    analytics_columns: Optional[List[str]] = None

    _columns: List[str] = field(
        default_factory=lambda: [
            "ts",
            "run_id",
            "seed",
            "event_type",
            "point",
            "rolls_since_point",
            "on_comeout",
            "mode",
            "units",
            "bankroll",
            "source",
            "id",
            "action",
            "bet_type",
            "amount",
            "notes",
            "extra",
        ]
    )

    # Track whether we’ve performed the first write (to control truncate vs append when append=False)
    _first_write_done: bool = field(default=False, init=False)

    _analytics_columns_normalized: List[str] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.analytics_columns:
            return
        seen: set[str] = set()
        for col in self.analytics_columns:
            col_str = str(col)
            if not col_str:
                continue
            if col_str not in seen:
                seen.add(col_str)
                self._analytics_columns_normalized.append(col_str)
                if col_str not in self._columns:
                    self._columns.append(col_str)

    # -------- convenience helpers (non-breaking) --------

    def identity(self) -> Dict[str, Any]:
        """Return run identity for summary/report writers."""
        return {"run_id": self.run_id, "seed": self.seed}

    @property
    def path_str(self) -> str:
        """Normalized CSV path as a string."""
        try:
            return str(Path(self.path))
        except Exception:
            return str(self.path)

    # ----------------------------------------------------

    def _ensure_parent(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def _has_header_row(self) -> bool:
        """
        Detect whether the CSV file already contains the exact header line.
        Skips comment lines that start with '#'.
        """
        p = Path(self.path)
        if not p.exists():
            return False
        try:
            with p.open("r", encoding="utf-8") as f:
                for _ in range(100):  # cheap scan of beginning
                    line = f.readline()
                    if not line:
                        break
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue
                    # first non-comment content line
                    expected_prefix = "ts,run_id,seed,"
                    return s.startswith(expected_prefix)
            return False
        except Exception:
            # If unreadable, be conservative and say no header
            return False

    def _needs_header(self) -> bool:
        """
        We need to write the header if the file either doesn't exist,
        is empty, or exists with only comment lines and no actual header row.
        """
        p = Path(self.path)
        if not p.exists():
            return True
        try:
            if p.stat().st_size == 0:
                return True
        except Exception:
            # if stat fails, try to write a header
            return True
        return not self._has_header_row()

    def _open_mode(self) -> str:
        """
        Decide file mode based on append flag and whether we've already written once.
        """
        if self.append:
            return "a"
        # append=False → first write should truncate, subsequent writes should append
        return "w" if not self._first_write_done else "a"

    def ensure_header(self) -> None:
        """
        Ensure the canonical CSV header line exists immediately after any optional cover-sheet.
        """
        self._ensure_parent()
        if not self._needs_header():
            return
        with open(self.path, self._open_mode(), newline="", encoding="utf-8") as f:
            _write_csv_header(f, self._columns)
        # mark that at least one write happened (controls future mode selection when append=False)
        self._first_write_done = True

    # ---------------- P5C4: cover-sheet writer (optional, non-breaking) ----------------

    def write_cover_sheet(
        self,
        summary: Dict[str, Any] | None = None,
        source_files: Dict[str, Any] | None = None,
        identity: Dict[str, Any] | None = None,
        *,
        report_version: str = "1",
        extra: Dict[str, Any] | None = None,
    ) -> bool:
        """
        Write a comment-only preamble to a *new* CSV file.
        Safe to call multiple times: only writes if the file is empty or missing.
        Returns True on write, False if skipped or on failure.
        """
        try:
            self._ensure_parent()
            p = Path(self.path)
            # Only write a cover if file is missing or empty.
            if p.exists():
                try:
                    if p.stat().st_size > 0:
                        return False
                except Exception:
                    # If stat fails, fall through and try to write
                    pass

            # Build cover lines (all begin with '# ', followed by a blank line)
            def _dump(obj: Any) -> str:
                return json.dumps(
                    obj or {}, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                )

            lines: List[str] = []
            lines.append(f"# report_version: {report_version}")
            lines.append(f"# created_utc: {_iso_now()}")
            lines.append(f"# run_id: {self.run_id if self.run_id is not None else ''}")
            lines.append(f"# seed: {self.seed if self.seed is not None else ''}")
            lines.append(f"# identity: {_dump(identity)}")
            lines.append(f"# source_files: {_dump(source_files)}")
            lines.append(f"# summary: {_dump(summary)}")
            if extra:
                lines.append(f"# extra: {_dump(extra)}")
            lines.append("")  # blank line before header/content

            with open(self.path, self._open_mode(), encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

            # Do NOT mark _first_write_done here; header/content may still need to be written.
            return True
        except Exception:
            return False

    # ---------------- core event journaling ----------------

    def write_actions(
        self,
        actions: Iterable[Dict[str, Any]],
        snapshot: Dict[str, Any] | None = None,
        *,
        controller: Any | None = None,
    ) -> int:
        acts = list(actions or [])
        if not acts:
            self.ensure_header()
            return 0

        snap = snapshot or {}
        adapter_snapshot = None
        if controller is not None:
            _append_adapter_snapshot_fields_if_enabled(controller, {}, self._columns)
        else:
            adapter_snapshot = (
                snap.get("adapter_snapshot")
                if isinstance(snap.get("adapter_snapshot"), dict)
                else None
            )
            adapter_fields = ["bankroll_after", "bet_6", "bet_8"]
            if adapter_snapshot is not None:
                for field in adapter_fields:
                    if field not in self._columns:
                        self._columns.append(field)

        self._ensure_parent()
        mode_flag = self._open_mode()
        write_header = self._needs_header()

        with open(self.path, mode_flag, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self._columns, extrasaction="ignore")
            if write_header:
                _write_csv_header(f, self._columns)

            event_type = _as_str(snap.get("event_type") or snap.get("type") or "")
            point = snap.get("point")
            rolls_since_point = snap.get("rolls_since_point")
            on_comeout = snap.get("on_comeout")
            mode_val = _as_str(snap.get("mode"))
            units = _coerce_num(snap.get("units"))
            bankroll = _coerce_num(snap.get("bankroll"))
            adapter_snapshot = adapter_snapshot or {}

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
                    "rolls_since_point": (
                        int(_coerce_num(rolls_since_point))
                        if _coerce_num(rolls_since_point) is not None
                        else ""
                    ),
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

                if controller is not None:
                    _append_adapter_snapshot_fields_if_enabled(controller, row, self._columns)
                else:
                    if "bankroll_after" in self._columns:
                        bankroll_after = snap.get("bankroll_after")
                        if bankroll_after is None and isinstance(adapter_snapshot, dict):
                            bankroll_after = adapter_snapshot.get("bankroll")
                        coerced = _coerce_num(bankroll_after)
                        row["bankroll_after"] = coerced if coerced is not None else 0
                    if "bet_6" in self._columns:
                        bet6 = snap.get("bet_6")
                        if bet6 is None and isinstance(adapter_snapshot, dict):
                            bets_map = adapter_snapshot.get("bets")
                            if isinstance(bets_map, dict):
                                bet6 = bets_map.get("6")
                        bet6_num = _coerce_num(bet6)
                        row["bet_6"] = bet6_num if bet6_num is not None else 0
                    if "bet_8" in self._columns:
                        bet8 = snap.get("bet_8")
                        if bet8 is None and isinstance(adapter_snapshot, dict):
                            bets_map = adapter_snapshot.get("bets")
                            if isinstance(bets_map, dict):
                                bet8 = bets_map.get("8")
                        bet8_num = _coerce_num(bet8)
                        row["bet_8"] = bet8_num if bet8_num is not None else 0

                if self._analytics_columns_normalized:
                    for col in self._analytics_columns_normalized:
                        if col in ("hand_id", "roll_in_hand"):
                            num = _coerce_num(snap.get(col))
                            row[col] = int(num) if num is not None else ""
                        elif col in ("bankroll_after", "drawdown_after"):
                            num = _coerce_num(snap.get(col))
                            row[col] = num if num is not None else ""
                        else:
                            val = snap.get(col)
                            row[col] = _as_str(val) if val is not None else ""

                try:
                    writer.writerow(row)
                    rows_written += 1
                except Exception:
                    # Fail-open: skip problematic rows but keep file usable
                    continue

        # mark that at least one write happened (controls future mode selection when append=False)
        self._first_write_done = True
        return rows_written

    # ---------------- P5C1: summary writer ----------------

    def write_summary(
        self, summary: Dict[str, Any], snapshot: Dict[str, Any] | None = None
    ) -> bool:
        """
        Append a single 'summary' row with the given summary dict in 'extra'.
        Returns True on success, False on failure. Never raises.

        NOTE: Tests also allow controllers to emit the summary row via write_actions()
        using a benign 'switch_mode' envelope (id='summary:run', notes='end_of_run').
        This method remains for backwards-compat and explicit usage.
        """
        try:
            self._ensure_parent()
            mode_flag = self._open_mode()
            write_header = self._needs_header()
            with open(self.path, mode_flag, newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self._columns, extrasaction="ignore")
                if write_header:
                    _write_csv_header(f, self._columns)

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
                    "id": "summary:run",
                    "action": "switch_mode",
                    "bet_type": "",
                    "amount": "",
                    "notes": "end_of_run",
                    "extra": _as_str(summary),
                }
                if self._analytics_columns_normalized:
                    for col in self._analytics_columns_normalized:
                        row.setdefault(col, "")
                writer.writerow(row)

            # mark that at least one write happened (controls future mode selection when append=False)
            self._first_write_done = True
            return True
        except Exception:
            return False
