"""Resumable end-to-end pipeline orchestration."""

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from clipper.audio import analyze_audio
from clipper.cache import StageCache, fingerprint
from clipper.candidates import generate_candidates
from clipper.config import ClipperConfig
from clipper.logging import build_logger
from clipper.media import probe_media
from clipper.models import (
    AudioInterval,
    Candidate,
    MediaInfo,
    RankedCandidate,
    RenderResult,
    Scene,
    Selection,
    TranscriptSegment,
)
from clipper.providers import OllamaRanker, OpenAICompatibleRanker, Ranker
from clipper.ranking import HeuristicRanker, automatic_clip_count, choose_diverse
from clipper.refine import refine_candidate
from clipper.reframe import analyze_subject_path, crop_dimensions, crop_expression
from clipper.render import (
    available_encoder,
    build_original_command,
    build_vertical_command,
    render_with_fallback,
)
from clipper.scenes import detect_scenes
from clipper.state import Stage, StageStatus
from clipper.subtitles import build_caption_cues, render_ass, render_srt
from clipper.transcription import transcribe_media

ProgressCallback = Callable[[Stage, StageStatus, str], None]


@dataclass(frozen=True)
class PipelineServices:
    probe: Callable[[Path], MediaInfo] = probe_media
    transcribe: Callable[[Path, MediaInfo, ClipperConfig], list[TranscriptSegment]] = (
        transcribe_media
    )
    scenes: Callable[[Path, float, float], list[Scene]] = detect_scenes
    audio: Callable[[Path], list[AudioInterval]] = analyze_audio


class PipelineResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    source: Path
    episode_directory: Path
    dry_run: bool
    selections: tuple[Selection, ...]
    renders: tuple[RenderResult, ...] = ()


class ClipperPipeline:
    def __init__(
        self,
        config: ClipperConfig,
        services: PipelineServices | None = None,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.config = config
        self.services = services or PipelineServices()
        self.progress = progress or (lambda _stage, _status, _message: None)
        self._logger: Any | None = None
        self._encoder: str | None = None

    def run(self, source: Path, dry_run: bool = False) -> PipelineResult:
        source = source.resolve(strict=True)
        episode_directory = self.config.output.resolve() / episode_output_name(source)
        episode_directory.mkdir(parents=True, exist_ok=True)
        cache = StageCache(episode_directory / ".cache")
        source_key = cache.source_fingerprint(source)
        logger = build_logger(episode_directory / "run.jsonl")
        self._logger = logger

        media = self._cached_model(
            cache,
            Stage.PROBE,
            fingerprint({"source": source_key, "ffprobe": 1}),
            MediaInfo,
            lambda: self.services.probe(source),
        )
        transcript = self._cached_models(
            cache,
            Stage.TRANSCRIPT,
            fingerprint(
                {
                    "source": source_key,
                    "model": self.config.whisper_model,
                    "language": self.config.language,
                    "device": self.config.device,
                    "compute_type": self.config.compute_type,
                    "embedded": self.config.use_embedded_subtitles,
                    "subtitle_parser": 2,
                }
            ),
            TranscriptSegment,
            lambda: self.services.transcribe(source, media, self.config),
        )
        if not transcript:
            raise RuntimeError("transcription produced no dialogue segments")
        scenes = self._cached_models(
            cache,
            Stage.SCENES,
            fingerprint({"source": source_key, "threshold": self.config.scene_threshold}),
            Scene,
            lambda: self.services.scenes(source, media.duration, self.config.scene_threshold),
        )
        audio = self._cached_models(
            cache,
            Stage.AUDIO,
            fingerprint(
                {
                    "source": source_key,
                    "sample_rate": 8000,
                    "audio_codec": media.audio_codec,
                }
            ),
            AudioInterval,
            lambda: [] if media.audio_codec is None else self.services.audio(source),
        )
        candidate_config = {
            "min_duration": self.config.min_duration,
            "max_duration": self.config.max_duration,
            "target_duration": self.config.target_duration,
        }
        candidates = self._cached_models(
            cache,
            Stage.CANDIDATES,
            fingerprint(
                {
                    "source": source_key,
                    "config": candidate_config,
                    "transcript": _dump(transcript),
                    "scenes": _dump(scenes),
                    "audio": _dump(audio),
                }
            ),
            Candidate,
            lambda: generate_candidates(
                transcript, scenes, self.config, media.duration, audio=audio
            ),
        )
        if not candidates:
            raise RuntimeError(
                "no candidates met the duration rules; lower --min-duration or inspect "
                "transcript.json"
            )
        ranker = self._ranker()
        ranked = self._cached_models(
            cache,
            Stage.RANKING,
            fingerprint(
                {
                    "candidates": _dump(candidates),
                    "ranker": self.config.ranker,
                    "model": (
                        self.config.ollama_model
                        if self.config.ranker == "ollama"
                        else self.config.llm_model
                    ),
                    "ranking_prompt": 2,
                }
            ),
            RankedCandidate,
            lambda: ranker.rank(candidates),
        )
        if self.config.clips == "auto":
            diverse_pool = choose_diverse(ranked, 8, minimum=1)
            clip_count = automatic_clip_count(diverse_pool, media.duration)
            diverse = diverse_pool[:clip_count]
        else:
            diverse = choose_diverse(ranked, self.config.clips)
        selections = tuple(
            Selection(
                rank=index,
                candidate=refine_candidate(item.candidate, transcript, self.config, media.duration),
                score=item.score,
            )
            for index, item in enumerate(diverse, start=1)
        )
        self._event(
            logger, Stage.REFINEMENT, StageStatus.COMPLETED, f"selected {len(selections)} clips"
        )
        _write_json(
            episode_directory / "transcript.json",
            {"source": str(source), "segments": _dump(transcript)},
        )
        _write_json(
            episode_directory / "ranking.json",
            {
                "source": str(source),
                "selected_ids": [item.candidate.id for item in selections],
                "candidates": _dump(ranked),
            },
        )
        renders: tuple[RenderResult, ...] = ()
        if not dry_run:
            self._encoder = None
            renders = tuple(
                self._render_one(
                    source,
                    source_key,
                    media,
                    transcript,
                    selection,
                    episode_directory,
                    logger,
                )
                for selection in selections
            )
            _remove_stale_render_directories(episode_directory, selections)
        return PipelineResult(
            source=source,
            episode_directory=episode_directory,
            dry_run=dry_run,
            selections=selections,
            renders=renders,
        )

    def _ranker(self) -> Ranker:
        if self.config.ranker == "ollama":
            return OllamaRanker(self.config.ollama_base_url, self.config.ollama_model)
        if self.config.ranker == "openai-compatible":
            assert self.config.llm_base_url is not None
            assert self.config.llm_model is not None
            return OpenAICompatibleRanker(
                self.config.llm_base_url, self.config.llm_model, self.config.llm_api_key_env
            )
        return HeuristicRanker()

    def _render_one(
        self,
        source: Path,
        source_key: str,
        media: MediaInfo,
        transcript: list[TranscriptSegment],
        selection: Selection,
        episode_directory: Path,
        logger: Any,
    ) -> RenderResult:
        clip_directory = episode_directory / f"clip_{selection.rank:02d}"
        clip_directory.mkdir(parents=True, exist_ok=True)
        candidate = selection.candidate
        original = clip_directory / "original.mp4"
        vertical = clip_directory / "vertical.mp4" if self.config.vertical else None
        subtitle_path = clip_directory / "subtitles.srt" if self.config.captions else None
        ass_path = clip_directory / ".captions.ass" if self.config.captions else None
        metadata_path = clip_directory / "metadata.json"
        render_key = fingerprint(
            {
                "source": source_key,
                "candidate": candidate.model_dump(mode="json"),
                "vertical": self.config.vertical,
                "captions": self.config.captions,
                "caption_style": self.config.caption_style,
                "playback_speed": self.config.playback_speed,
                "hardware_encoding": self.config.hardware_encoding,
                "workers": self.config.workers,
                "render_version": 4,
            }
        )
        resumed = self._resume_render(metadata_path, render_key, original, vertical, subtitle_path)
        if resumed is not None and not self.config.overwrite:
            self._event(logger, Stage.RENDER, StageStatus.CACHED, f"clip {selection.rank}: cached")
            return resumed
        self._event(logger, Stage.RENDER, StageStatus.STARTED, f"clip {selection.rank}: started")
        try:
            cues = build_caption_cues(
                transcript,
                clip_start=candidate.start,
                clip_end=candidate.end,
                playback_speed=self.config.playback_speed,
                emphasize=self.config.emphasize_words,
            )
            if subtitle_path and ass_path:
                subtitle_path.write_text(render_srt(cues), encoding="utf-8")
                ass_path.write_text(
                    render_ass(cues, style=self.config.caption_style), encoding="utf-8"
                )
            if self._encoder is None:
                self._encoder = available_encoder(self.config.hardware_encoding)
            encoder = self._encoder
            original_gpu = build_original_command(
                source,
                original,
                candidate.start,
                candidate.end,
                encoder=encoder,
                threads=self.config.workers,
                playback_speed=self.config.playback_speed,
            )
            original_cpu = build_original_command(
                source,
                original,
                candidate.start,
                candidate.end,
                encoder="libx264",
                threads=self.config.workers,
                playback_speed=self.config.playback_speed,
            )
            render_with_fallback(original_gpu, original_cpu)
            if vertical:
                crop_width, _height = crop_dimensions(media.width, media.height)
                points = analyze_subject_path(
                    source,
                    candidate.start,
                    candidate.end,
                    media.width,
                    crop_width,
                )
                vertical_gpu = build_vertical_command(
                    source,
                    vertical,
                    candidate.start,
                    candidate.end,
                    media.width,
                    media.height,
                    crop_expression(points),
                    encoder=encoder,
                    subtitle_path=ass_path,
                    threads=self.config.workers,
                    playback_speed=self.config.playback_speed,
                )
                vertical_cpu = build_vertical_command(
                    source,
                    vertical,
                    candidate.start,
                    candidate.end,
                    media.width,
                    media.height,
                    crop_expression(points),
                    encoder="libx264",
                    subtitle_path=ass_path,
                    threads=self.config.workers,
                    playback_speed=self.config.playback_speed,
                )
                render_with_fallback(vertical_gpu, vertical_cpu)
            result = RenderResult(
                clip=selection.rank,
                original=original,
                vertical=vertical,
                subtitles=subtitle_path,
            )
            status = StageStatus.COMPLETED
        except Exception as error:  # isolate failures by clip
            result = RenderResult(
                clip=selection.rank,
                original=original if original.exists() else None,
                vertical=vertical if vertical and vertical.exists() else None,
                subtitles=subtitle_path if subtitle_path and subtitle_path.exists() else None,
                error=str(error),
            )
            status = StageStatus.FAILED
        metadata = {
            "source_file": str(source),
            "start": candidate.start,
            "end": candidate.end,
            "duration": candidate.duration / self.config.playback_speed,
            "source_duration": candidate.duration,
            "playback_speed": self.config.playback_speed,
            "transcript": candidate.transcript,
            **selection.score.model_dump(),
            "rank": selection.rank,
            "render_fingerprint": render_key,
            "files": result.model_dump(mode="json"),
        }
        _write_json(metadata_path, metadata)
        self._event(logger, Stage.RENDER, status, f"clip {selection.rank}: {status}")
        return result

    def _resume_render(
        self,
        metadata_path: Path,
        render_key: str,
        original: Path,
        vertical: Path | None,
        subtitles: Path | None,
    ) -> RenderResult | None:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            result = RenderResult.model_validate(metadata["files"])
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            return None
        required = [original]
        if vertical is not None:
            required.append(vertical)
        if subtitles is not None:
            required.append(subtitles)
        if (
            metadata.get("render_fingerprint") != render_key
            or result.error is not None
            or not all(path.is_file() for path in required)
        ):
            return None
        return result

    def _cached_model(
        self,
        cache: StageCache,
        stage: Stage,
        key: str,
        model: type[BaseModel],
        producer: Callable[[], BaseModel],
    ) -> Any:
        value = cache.load(stage.value, key)
        if value is not None:
            self._notify(stage, StageStatus.CACHED, stage.value)
            return model.model_validate(value)
        self._notify(stage, StageStatus.STARTED, stage.value)
        result = producer()
        cache.save(stage.value, key, result.model_dump(mode="json"))
        self._notify(stage, StageStatus.COMPLETED, stage.value)
        return result

    def _cached_models(
        self,
        cache: StageCache,
        stage: Stage,
        key: str,
        model: type[BaseModel],
        producer: Callable[[], list[Any]],
    ) -> list[Any]:
        value = cache.load(stage.value, key)
        if value is not None:
            self._notify(stage, StageStatus.CACHED, stage.value)
            return [model.model_validate(item) for item in value]
        self._notify(stage, StageStatus.STARTED, stage.value)
        result = producer()
        cache.save(stage.value, key, _dump(result))
        self._notify(stage, StageStatus.COMPLETED, stage.value)
        return result

    def _event(self, logger: Any, stage: Stage, status: StageStatus, message: str) -> None:
        del logger
        self._notify(stage, status, message)

    def _notify(self, stage: Stage, status: StageStatus, message: str) -> None:
        self.progress(stage, status, message)
        if self._logger is not None:
            self._logger.info(
                message, extra={"event": {"stage": stage.value, "status": status.value}}
            )


def episode_output_name(source: Path) -> str:
    stem = source.stem
    safe = re.sub(r"[^\w.-]+", "_", stem, flags=re.UNICODE).strip("._-")
    return safe or "episode"


def _dump(models: list[Any] | tuple[Any, ...]) -> list[Any]:
    return [
        item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in models
    ]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _remove_stale_render_directories(
    episode_directory: Path, selections: tuple[Selection, ...]
) -> None:
    active = {f"clip_{selection.rank:02d}" for selection in selections}
    for path in episode_directory.iterdir():
        if (
            path.name in active
            or re.fullmatch(r"clip_\d+", path.name) is None
            or not path.is_dir()
            or path.is_symlink()
            or not (path / "metadata.json").is_file()
        ):
            continue
        shutil.rmtree(path)
