"""On-disk queue implementation — one JSON file per frame."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Iterator

from ...common.paths import queue_dir

log = logging.getLogger("dta.queue")

_MAX_FILES = 5000


def enqueue(frame: dict[str, Any]) -> None:
    d = queue_dir()
    d.mkdir(parents=True, exist_ok=True)
    name = f"{int(time.time() * 1000)}-{id(frame) & 0xffff:04x}.json"
    (d / name).write_text(json.dumps(frame, separators=(",", ":")), encoding="utf-8")
    files = sorted(d.glob("*.json"))
    if len(files) > _MAX_FILES:
        for old in files[: len(files) - _MAX_FILES]:
            try:
                old.unlink()
            except OSError:
                pass


def drain() -> Iterator[tuple[Path, dict[str, Any]]]:
    d = queue_dir()
    if not d.exists():
        return
    for f in sorted(d.glob("*.json")):
        try:
            yield f, json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("queue: dropping unreadable %s (%s)", f, exc)
            try:
                f.unlink()
            except OSError:
                pass


def depth() -> int:
    d = queue_dir()
    return sum(1 for _ in d.glob("*.json")) if d.exists() else 0
