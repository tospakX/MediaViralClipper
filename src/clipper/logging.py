"""Structured JSONL run logging."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JsonlHandler(logging.Handler):
    def __init__(self, path: Path) -> None:
        super().__init__()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path

    def emit(self, record: logging.LogRecord) -> None:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "name": record.name,
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
        }
        event = getattr(record, "event", None)
        if isinstance(event, dict):
            payload.update(event)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n"
            )


def build_logger(path: Path) -> logging.Logger:
    logger = logging.getLogger(f"clipper.{path.resolve()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        logger.addHandler(JsonlHandler(path))
    return logger
