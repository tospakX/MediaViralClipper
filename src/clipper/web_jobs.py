"""Thread-safe, bounded pipeline jobs for the local web interface."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Annotated, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from clipper.cache import clear_stage_caches
from clipper.config import ClipperConfig
from clipper.models import RenderResult, Selection
from clipper.pipeline import ClipperPipeline, PipelineResult, ProgressCallback
from clipper.state import Stage, StageStatus

JobStatus = Literal["queued", "running", "completed", "failed"]
BatchStatus = Literal["queued", "running", "completed"]
SUPPORTED_MEDIA_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}

_STAGE_PROGRESS = {
    Stage.PROBE: 8,
    Stage.TRANSCRIPT: 28,
    Stage.SCENES: 40,
    Stage.AUDIO: 50,
    Stage.CANDIDATES: 62,
    Stage.RANKING: 76,
    Stage.REFINEMENT: 86,
    Stage.RENDER: 94,
}


def default_output_directory() -> Path:
    return Path.home() / "Downloads" / "MediaViralClipper"


class WebJobOptions(BaseModel):
    """Shared browser controls translated into the canonical pipeline config."""

    model_config = ConfigDict(extra="forbid")

    output: Path = Field(default_factory=default_output_directory)
    clips: Annotated[int, Field(ge=1, le=10)] | Literal["auto"] = "auto"
    min_duration: float = Field(default=15, gt=0)
    max_duration: float = Field(default=40, gt=0, le=300)
    vertical: bool = True
    captions: bool = True
    caption_style: Literal["default", "bold", "minimal"] = "bold"
    playback_speed: float = Field(default=1.1, ge=0.5, le=2.0)
    dry_run: bool = False
    whisper_model: str = "small"
    language: str | None = None
    device: Literal["auto", "cpu", "cuda"] = "auto"
    hardware_encoding: Literal["auto", "cpu", "nvenc"] = "auto"
    workers: int = Field(default=2, ge=1, le=16)
    ranker: Literal["heuristic", "ollama", "openai-compatible"] = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:1.7b"
    llm_base_url: str | None = None
    llm_model: str | None = None

    @field_validator("output", mode="before")
    @classmethod
    def expand_user_path(cls, value: object) -> object:
        if isinstance(value, (str, Path)):
            return Path(value).expanduser()
        return value

    @model_validator(mode="after")
    def validate_durations(self) -> WebJobOptions:
        if self.min_duration > self.max_duration:
            raise ValueError("min_duration must not exceed max_duration")
        return self

    def to_config(self) -> ClipperConfig:
        target = min(max(28.0, self.min_duration), self.max_duration)
        return ClipperConfig(
            clips=self.clips,
            min_duration=self.min_duration,
            max_duration=self.max_duration,
            target_duration=target,
            vertical=self.vertical,
            captions=self.captions,
            caption_style=self.caption_style,
            playback_speed=self.playback_speed,
            output=self.output,
            whisper_model=self.whisper_model,
            language=self.language,
            device=self.device,
            hardware_encoding=self.hardware_encoding,
            workers=self.workers,
            ranker=self.ranker,
            ollama_base_url=self.ollama_base_url,
            ollama_model=self.ollama_model,
            llm_base_url=self.llm_base_url,
            llm_model=self.llm_model,
        )


class WebJobRequest(WebJobOptions):
    """One local media file and its processing controls."""

    source: Path

    @field_validator("source", mode="before")
    @classmethod
    def expand_source_path(cls, value: object) -> object:
        if isinstance(value, (str, Path)):
            return Path(value).expanduser()
        return value

    @model_validator(mode="after")
    def validate_source_file(self) -> WebJobRequest:
        if not self.source.is_file():
            raise ValueError(f"source does not exist or is not a file: {self.source}")
        return self


class WebBatchRequest(WebJobOptions):
    """A local media file or folder expanded into ordinary pipeline jobs."""

    source: Path

    @field_validator("source", mode="before")
    @classmethod
    def expand_source_path(cls, value: object) -> object:
        if isinstance(value, (str, Path)):
            return Path(value).expanduser()
        return value

    @model_validator(mode="after")
    def validate_source_exists(self) -> WebBatchRequest:
        if not self.source.exists():
            raise ValueError(f"source does not exist: {self.source}")
        return self

    def to_jobs(self) -> tuple[WebJobRequest, ...]:
        options = self.model_dump(exclude={"source", "output"})
        return tuple(
            WebJobRequest(
                source=source,
                output=(
                    self.output / source.relative_to(self.source).parent
                    if self.source.is_dir()
                    else self.output
                ),
                **options,
            )
            for source in discover_media_files(self.source)
        )


def discover_media_files(source: Path, limit: int = 100) -> tuple[Path, ...]:
    """Resolve a file or recursively discover a stable batch of local episodes."""
    source = source.expanduser()
    if source.is_file():
        candidates = [source] if source.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS else []
    elif source.is_dir():
        candidates = sorted(
            (
                path
                for path in source.rglob("*")
                if path.is_file() and path.suffix.lower() in SUPPORTED_MEDIA_EXTENSIONS
            ),
            key=lambda path: str(path.relative_to(source)).casefold(),
        )
    else:
        raise ValueError(f"source does not exist: {source}")
    if not candidates:
        raise ValueError(f"no supported media files found in {source}")
    if len(candidates) > limit:
        raise ValueError(f"found {len(candidates)} episodes; the batch limit is {limit}")
    return tuple(candidates)


class JobEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: str
    status: str
    progress: int = Field(ge=0, le=100)
    message: str
    occurred_at: datetime


class JobSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    message: str
    source: Path
    dry_run: bool
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_directory: Path | None = None
    selections: tuple[Selection, ...] = ()
    renders: tuple[RenderResult, ...] = ()
    events: tuple[JobEvent, ...] = ()
    error: str | None = None


class BatchSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    status: BatchStatus
    progress: int = Field(ge=0, le=100)
    total: int = Field(ge=1, le=100)
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    jobs: tuple[JobSnapshot, ...]


class PipelineRunner(Protocol):
    def run(self, path: Path, dry_run: bool) -> PipelineResult: ...


PipelineFactory = Callable[[ClipperConfig, ProgressCallback], PipelineRunner]


class JobManager:
    def __init__(
        self,
        pipeline_factory: PipelineFactory | None = None,
        max_workers: int = 1,
    ) -> None:
        self._pipeline_factory = pipeline_factory or (
            lambda config, progress: ClipperPipeline(config, progress=progress)
        )
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="clipper-job"
        )
        self._lock = RLock()
        self._jobs: dict[str, JobSnapshot] = {}
        self._futures: dict[str, Future[None]] = {}
        self._batches: dict[str, tuple[str, ...]] = {}
        self._output_roots: set[Path] = set()
        self._closed = False

    def start(self, request: WebJobRequest) -> str:
        with self._lock:
            if self._closed:
                raise RuntimeError("job manager is closed")
            output_root = request.output.expanduser().resolve()
            if output_root not in self._output_roots:
                clear_stage_caches(output_root)
                self._output_roots.add(output_root)
            job_id = uuid4().hex
            self._jobs[job_id] = JobSnapshot(
                id=job_id,
                status="queued",
                progress=0,
                message="Waiting for the cut room",
                source=request.source.resolve(),
                dry_run=request.dry_run,
                created_at=_now(),
            )
            self._futures[job_id] = self._executor.submit(self._execute, job_id, request)
            return job_id

    def start_batch(self, request: WebBatchRequest) -> str:
        jobs = request.to_jobs()
        with self._lock:
            if self._closed:
                raise RuntimeError("job manager is closed")
            batch_id = uuid4().hex
            self._batches[batch_id] = tuple(self.start(job) for job in jobs)
            return batch_id

    def get_batch(self, batch_id: str) -> BatchSnapshot:
        with self._lock:
            try:
                job_ids = self._batches[batch_id]
            except KeyError as error:
                raise KeyError(f"unknown batch: {batch_id}") from error
            jobs = tuple(self._jobs[job_id].model_copy(deep=True) for job_id in job_ids)
        counts = {
            status: sum(job.status == status for job in jobs)
            for status in ("queued", "running", "completed", "failed")
        }
        terminal = counts["completed"] + counts["failed"]
        status: BatchStatus = (
            "completed"
            if terminal == len(jobs)
            else "running"
            if counts["running"] or terminal
            else "queued"
        )
        return BatchSnapshot(
            id=batch_id,
            status=status,
            progress=round(sum(job.progress for job in jobs) / len(jobs)),
            total=len(jobs),
            queued=counts["queued"],
            running=counts["running"],
            completed=counts["completed"],
            failed=counts["failed"],
            jobs=jobs,
        )

    def get(self, job_id: str) -> JobSnapshot:
        with self._lock:
            try:
                return self._jobs[job_id].model_copy(deep=True)
            except KeyError as error:
                raise KeyError(f"unknown job: {job_id}") from error

    def wait(self, job_id: str, timeout: float | None = None) -> JobSnapshot:
        with self._lock:
            try:
                future = self._futures[job_id]
            except KeyError as error:
                raise KeyError(f"unknown job: {job_id}") from error
        future.result(timeout=timeout)
        return self.get(job_id)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            output_roots = tuple(self._output_roots)
        self._executor.shutdown(wait=True, cancel_futures=False)
        for output_root in output_roots:
            clear_stage_caches(output_root)

    def _execute(self, job_id: str, request: WebJobRequest) -> None:
        self._update(
            job_id,
            status="running",
            message="Opening the source",
            started_at=_now(),
        )

        def progress(stage: Stage, status: StageStatus, message: str) -> None:
            proposed = _STAGE_PROGRESS[stage]
            if status == StageStatus.STARTED:
                proposed = max(1, proposed - 5)
            with self._lock:
                current = self._jobs[job_id]
                value = max(current.progress, proposed)
                event = JobEvent(
                    stage=stage.value,
                    status=status.value,
                    progress=value,
                    message=message,
                    occurred_at=_now(),
                )
                self._jobs[job_id] = current.model_copy(
                    update={
                        "progress": value,
                        "message": _friendly_message(stage, status),
                        "events": (*current.events, event),
                    }
                )

        try:
            pipeline = self._pipeline_factory(request.to_config(), progress)
            result = pipeline.run(request.source.resolve(), dry_run=request.dry_run)
            self._update(
                job_id,
                status="completed",
                progress=100,
                message=(
                    "Ranking ready—nothing rendered"
                    if request.dry_run
                    else f"{len(result.selections)} cuts ready to review"
                ),
                output_directory=result.episode_directory,
                selections=result.selections,
                renders=result.renders,
                finished_at=_now(),
            )
        except Exception as error:
            self._update(
                job_id,
                status="failed",
                message="The job stopped—check the detail below",
                error=str(error),
                finished_at=_now(),
            )

    def _update(self, job_id: str, **values: object) -> None:
        with self._lock:
            self._jobs[job_id] = self._jobs[job_id].model_copy(update=values)


def _friendly_message(stage: Stage, status: StageStatus) -> str:
    verb = (
        "Reusing"
        if status == StageStatus.CACHED
        else {
            Stage.PROBE: "Inspecting media",
            Stage.TRANSCRIPT: "Reading dialogue",
            Stage.SCENES: "Finding scene changes",
            Stage.AUDIO: "Listening for reactions",
            Stage.CANDIDATES: "Building complete moments",
            Stage.RANKING: "Ranking the best bits",
            Stage.REFINEMENT: "Tightening the cuts",
            Stage.RENDER: "Rendering share-ready clips",
        }[stage]
    )
    return f"{verb} {stage.value}" if status == StageStatus.CACHED else verb


def _now() -> datetime:
    return datetime.now(UTC)
