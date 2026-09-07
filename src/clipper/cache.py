"""Atomic, deterministic cache storage for expensive stages."""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

CACHE_VERSION = 1


def clear_stage_caches(root: Path) -> tuple[Path, ...]:
    """Remove only pipeline-owned `.cache` directories below an output root."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        return ()
    cache_directories = sorted(
        (path for path in root.rglob(".cache") if path.is_dir() and not path.is_symlink()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in cache_directories:
        shutil.rmtree(directory)
    return tuple(cache_directories)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class StageCache:
    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @staticmethod
    def source_fingerprint(source: Path) -> str:
        resolved = source.resolve(strict=True)
        stat = resolved.stat()
        return fingerprint(
            {
                "path": str(resolved),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sample": _sample_digest(resolved),
            }
        )

    def load(self, stage: str, key: str) -> Any | None:
        path = self.directory / f"{stage}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        if payload.get("version") != CACHE_VERSION or payload.get("fingerprint") != key:
            return None
        return payload.get("data")

    def save(self, stage: str, key: str, data: Any) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"{stage}.json"
        payload = {"data": data, "fingerprint": key, "version": CACHE_VERSION}
        serialized = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
        )
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=self.directory, prefix=f".{stage}-", suffix=".tmp"
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        return destination


def _sample_digest(path: Path, sample_size: int = 64 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read(sample_size))
        if path.stat().st_size > sample_size:
            handle.seek(max(0, path.stat().st_size - sample_size))
            digest.update(handle.read(sample_size))
    return digest.hexdigest()
