from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class TraceRecorder:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.events: list[dict[str, Any]] = []

    def emit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        event = {
            "type": event_type,
            "ts": time.time(),
            "elapsed_ms": int((time.time() - self.started_at) * 1000),
            **payload,
        }
        self.events.append(event)
        return event

    def write(self, path: Path, run: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "trace_version": "1.0",
            "run": run,
            "events": self.events,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
