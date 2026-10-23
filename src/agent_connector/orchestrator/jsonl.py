"""Append-only JSONL writer for orchestrator call and event logs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, TextIO


class JsonlLogger:
    """Thread-hostile, asyncio-friendly append logger (one writer at a time)."""

    def __init__(self, path: Path | str | None) -> None:
        self._path = Path(path) if path is not None else None
        self._handle: TextIO | None = None

    def __enter__(self) -> JsonlLogger:
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self._path.open("a", encoding="utf-8")
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def emit(self, event: str, **fields: Any) -> None:
        if self._handle is None:
            return
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        self._handle.write(json.dumps(record, separators=(",", ":"), default=str))
        self._handle.write("\n")
        self._handle.flush()
