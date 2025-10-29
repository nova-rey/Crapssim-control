from __future__ import annotations

from typing import TextIO


def skip_csv_preamble(fh: TextIO) -> TextIO:
    """Advance a file handle past comment/blank preamble lines for CSV readers."""

    while True:
        pos = fh.tell()
        line = fh.readline()
        if not line:
            break
        if not line.strip():
            continue
        if line.startswith("#"):
            continue
        fh.seek(pos)
        break
    return fh
