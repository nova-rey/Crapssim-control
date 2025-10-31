from __future__ import annotations

import json
import os
import pathlib
import typing as t


def write_json_atomic(path: t.Union[str, pathlib.Path], payload: dict) -> None:
    """Atomically write *payload* as formatted JSON to *path*."""

    p = pathlib.Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)
