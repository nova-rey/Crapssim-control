from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(p: str | Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(p: str | Path) -> dict[str, Any]:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def write_json(p: str | Path, obj: dict[str, Any]) -> None:
    path = Path(p)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
