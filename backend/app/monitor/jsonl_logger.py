"""Structured JSONL logger for monitor events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlEventLogger:
    """Append monitor events as one JSON object per line."""

    def __init__(self, path: Path):
        self.path = path

    def log(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str, sort_keys=True))
            handle.write("\n")
