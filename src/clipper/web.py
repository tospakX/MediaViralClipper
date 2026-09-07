"""FastAPI application for the localhost cut-room interface."""

from __future__ import annotations

import argparse
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, TypedDict, cast

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, HTMLResponse
from starlette.middleware.base import RequestResponseEndpoint

from clipper.cache import clear_stage_caches
from clipper.doctor import SystemReport, inspect_system
from clipper.web_jobs import (
    BatchSnapshot,
    JobManager,
    JobSnapshot,
    WebBatchRequest,
    WebJobRequest,
    default_output_directory,
    discover_media_files,
)

STATIC_ROOT = Path(__file__).with_name("web_static")
Artifact = Literal["original", "vertical", "subtitles", "metadata"]


class LibraryClip(TypedDict):
    rank: int
    duration: float
    overall: float
    transcript: str
    explanation: str
    original: bool
    vertical: bool
    subtitles: bool


class LibraryEpisode(TypedDict):
    id: str
    name: str
    clips: list[LibraryClip]
    updated_at: float


def create_app(
    manager: JobManager | None = None,
    system_inspector: Callable[[], SystemReport | dict[str, object]] = inspect_system,
    startup_cache_root: Path | None = None,
) -> FastAPI:
    owns_manager = manager is None
    jobs = manager or JobManager()
    lifecycle_cache_root = startup_cache_root or default_output_directory()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        clear_stage_caches(lifecycle_cache_root)
        try:
            yield
        finally:
            try:
                if owns_manager:
                    jobs.close()
            finally:
                clear_stage_caches(lifecycle_cache_root)

    application = FastAPI(
        title="Media Viral Clipper",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.jobs = jobs

    @application.middleware("http")
    async def local_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home() -> Response:
        index = STATIC_ROOT / "index.html"
        if index.is_file():
            return FileResponse(index, media_type="text/html")
        return HTMLResponse("<title>Media Viral Clipper</title><h1>Media Viral Clipper</h1>")

    @application.get("/assets/{asset_name}", include_in_schema=False)
    def asset(asset_name: Literal["app.css", "app.js"]) -> FileResponse:
        path = STATIC_ROOT / asset_name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Asset not found")
        media_type = "text/css" if asset_name.endswith(".css") else "text/javascript"
        return FileResponse(path, media_type=media_type)

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "scope": "localhost"}

    @application.get("/api/system")
    def system() -> SystemReport | dict[str, object]:
        return system_inspector()

    @application.get("/api/files")
    def files(path: str | None = None) -> dict[str, object]:
        try:
            return browse_media_directory(path)
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.get("/api/scan")
    def scan(path: str) -> dict[str, object]:
        try:
            return scan_media_source(path)
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.get("/api/library")
    def library(output: str) -> dict[str, object]:
        try:
            return scan_output_library(output)
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.get("/api/library/artifact")
    def library_artifact(
        output: str, episode: str, rank: int, artifact: str, download: bool = False
    ) -> FileResponse:
        path = _library_artifact_path(output, episode, rank, artifact)
        media_types = {
            "original": "video/mp4",
            "vertical": "video/mp4",
            "subtitles": "application/x-subrip",
            "metadata": "application/json",
        }
        return FileResponse(
            path,
            media_type=media_types[artifact],
            filename=path.name if download else None,
        )

    @application.post("/api/jobs", status_code=status.HTTP_202_ACCEPTED)
    def start_job(request: WebJobRequest) -> dict[str, str]:
        return {"id": jobs.start(request)}

    @application.post("/api/batches", status_code=status.HTTP_202_ACCEPTED)
    def start_batch(request: WebBatchRequest) -> dict[str, str | int]:
        try:
            batch_id = jobs.start_batch(request)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"id": batch_id, "total": jobs.get_batch(batch_id).total}

    @application.get("/api/batches/{batch_id}", response_model=BatchSnapshot)
    def get_batch(batch_id: str) -> BatchSnapshot:
        try:
            return jobs.get_batch(batch_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Batch not found") from error

    @application.get("/api/jobs/{job_id}", response_model=JobSnapshot)
    def get_job(job_id: str) -> JobSnapshot:
        try:
            return jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Job not found") from error

    @application.get("/api/jobs/{job_id}/clips/{rank}/{artifact}")
    def clip_artifact(
        job_id: str, rank: int, artifact: str, download: bool = False
    ) -> FileResponse:
        if artifact not in {"original", "vertical", "subtitles", "metadata"}:
            raise HTTPException(status_code=404, detail="Artifact not found")
        known_artifact = cast(Artifact, artifact)
        try:
            snapshot = jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Job not found") from error
        path = _artifact_path(snapshot, rank, known_artifact)
        media_types = {
            "original": "video/mp4",
            "vertical": "video/mp4",
            "subtitles": "application/x-subrip",
            "metadata": "application/json",
        }
        return FileResponse(
            path,
            media_type=media_types[known_artifact],
            filename=path.name if download else None,
        )

    return application


def browse_media_directory(path: str | None = None) -> dict[str, object]:
    """List local folders and supported media for the browser-based path picker."""
    current = Path(path).expanduser() if path else Path.home()
    current = current.resolve(strict=True)
    if current.is_file():
        current = current.parent
    if not current.is_dir():
        raise ValueError(f"path is not a folder: {current}")
    entries = sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
    directories = [
        {"name": item.name, "path": str(item.resolve())}
        for item in entries
        if item.is_dir() and not item.name.startswith(".")
    ]
    files = [
        {"name": item.name, "path": str(item.resolve())}
        for item in entries
        if item.is_file()
        and item.suffix.lower() in {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}
    ]
    parent = None if current.parent == current else str(current.parent)
    return {"path": str(current), "parent": parent, "directories": directories, "files": files}


def scan_media_source(path: str) -> dict[str, object]:
    """Summarize a chosen file or recursive folder before it enters the queue."""
    source = Path(path).expanduser().resolve(strict=True)
    media = discover_media_files(source)
    sample = [
        item.name if source.is_file() else item.relative_to(source).as_posix() for item in media[:5]
    ]
    return {
        "path": str(source),
        "total": len(media),
        "kind": "video" if source.is_file() else "folder",
        "sample": sample,
    }


def scan_output_library(output: str) -> dict[str, object]:
    """Rebuild a lightweight preview index from completed output metadata."""
    root = Path(output).expanduser().resolve()
    if not root.exists():
        return {"output": str(root), "episodes": []}
    if not root.is_dir():
        raise ValueError(f"output is not a folder: {root}")
    episodes: dict[Path, list[LibraryClip]] = {}
    for metadata_path in root.rglob("clip_*/metadata.json"):
        clip_directory = metadata_path.parent
        episode_directory = clip_directory.parent
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            rank = int(metadata["rank"])
        except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError):
            continue
        clip: LibraryClip = {
            "rank": rank,
            "duration": float(metadata.get("duration", 0)),
            "overall": float(metadata.get("overall", 0)),
            "transcript": str(metadata.get("transcript", "")),
            "explanation": str(metadata.get("explanation", "")),
            "original": (clip_directory / "original.mp4").is_file(),
            "vertical": (clip_directory / "vertical.mp4").is_file(),
            "subtitles": (clip_directory / "subtitles.srt").is_file(),
        }
        if clip["original"] or clip["vertical"]:
            episodes.setdefault(episode_directory, []).append(clip)
    indexed: list[LibraryEpisode] = [
        {
            "id": directory.relative_to(root).as_posix(),
            "name": directory.name,
            "clips": sorted(clips, key=lambda item: item["rank"]),
            "updated_at": max(
                (directory / f"clip_{item['rank']:02d}" / "metadata.json").stat().st_mtime
                for item in clips
            ),
        }
        for directory, clips in episodes.items()
    ]
    indexed.sort(key=lambda item: item["updated_at"], reverse=True)
    return {"output": str(root), "episodes": indexed}


def _library_artifact_path(output: str, episode: str, rank: int, artifact: str) -> Path:
    filenames = {
        "original": "original.mp4",
        "vertical": "vertical.mp4",
        "subtitles": "subtitles.srt",
        "metadata": "metadata.json",
    }
    if artifact not in filenames:
        raise HTTPException(status_code=404, detail="Artifact not found")
    root = Path(output).expanduser().resolve()
    episode_directory = (root / episode).resolve()
    if not episode_directory.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Episode not found")
    path = (episode_directory / f"clip_{rank:02d}" / filenames[artifact]).resolve()
    if not path.is_relative_to(episode_directory) or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return path


def _artifact_path(snapshot: JobSnapshot, rank: int, artifact: Artifact) -> Path:
    output = snapshot.output_directory
    if snapshot.status != "completed" or output is None:
        raise HTTPException(status_code=404, detail="Job output is not ready")
    selection = next((item for item in snapshot.selections if item.rank == rank), None)
    if selection is None:
        raise HTTPException(status_code=404, detail="Clip not found")
    render = next((item for item in snapshot.renders if item.clip == rank), None)
    if artifact == "metadata":
        candidate = output / f"clip_{rank:02d}" / "metadata.json"
    elif render is None:
        raise HTTPException(status_code=404, detail="Clip was analyzed but not rendered")
    else:
        candidate = getattr(render, artifact)
        if candidate is None:
            raise HTTPException(status_code=404, detail=f"{artifact.title()} output is unavailable")
    output_root = output.resolve()
    resolved = Path(candidate).resolve()
    if not resolved.is_relative_to(output_root) or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Media Viral Clipper localhost UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true")
    arguments = parser.parse_args()
    uvicorn.run(
        "clipper.web:app",
        host=arguments.host,
        port=arguments.port,
        reload=arguments.reload,
    )


app = create_app()


if __name__ == "__main__":
    main()
