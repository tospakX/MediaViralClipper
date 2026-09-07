import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from clipper.config import ClipperConfig
from clipper.models import Candidate, Score, Selection
from clipper.pipeline import PipelineResult
from clipper.state import Stage, StageStatus
from clipper.web_jobs import JobManager, WebBatchRequest, WebJobRequest, discover_media_files


def _selection() -> Selection:
    candidate = Candidate(
        id="candidate-1",
        start=2,
        end=22,
        transcript="Wait, the moon is a sandwich? Apparently lunch has gravity!",
        segment_indices=(0, 1),
    )
    score = Score(
        humor=0.9,
        punchline=0.88,
        surprise=0.8,
        quotability=0.7,
        hook=0.86,
        standalone=0.8,
        pacing=0.75,
        reaction=0.7,
        retention=0.84,
        overall=0.85,
        explanation="Complete setup and a clean absurd punchline.",
    )
    return Selection(rank=1, candidate=candidate, score=score)


def test_request_rejects_missing_media_and_bad_duration(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="source"):
        WebJobRequest(source=tmp_path / "missing.mkv")

    source = tmp_path / "episode.mkv"
    source.touch()
    with pytest.raises(ValidationError, match="min_duration"):
        WebJobRequest(source=source, min_duration=41, max_duration=40)


def test_request_expands_home_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    source = tmp_path / "episode.mkv"
    source.touch()

    request = WebJobRequest(source="~/episode.mkv", output="~/Clips")

    assert request.source == source
    assert request.output == tmp_path / "Clips"


def test_batch_discovers_supported_media_recursively_in_stable_order(tmp_path: Path) -> None:
    library = tmp_path / "Episodes"
    (library / "season 2").mkdir(parents=True)
    (library / "B.MKV").touch()
    (library / "season 2" / "a.mp4").touch()
    (library / "notes.txt").touch()

    discovered = discover_media_files(library)

    assert discovered == (library / "B.MKV", library / "season 2" / "a.mp4")


def test_batch_rejects_more_than_one_hundred_episodes(tmp_path: Path) -> None:
    library = tmp_path / "Episodes"
    library.mkdir()
    for index in range(101):
        (library / f"episode-{index:03d}.mkv").touch()

    with pytest.raises(ValueError, match="100"):
        discover_media_files(library)


def test_batch_defaults_outputs_to_downloads_media_viral_clipper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    source = tmp_path / "episode.mkv"
    source.touch()

    request = WebBatchRequest(source=source)
    jobs = request.to_jobs()

    assert request.output == tmp_path / "Downloads" / "MediaViralClipper"
    assert jobs[0].source == source
    assert jobs[0].output == request.output


def test_web_jobs_default_to_automatic_clip_selection(tmp_path: Path) -> None:
    source = tmp_path / "episode.mkv"
    source.touch()

    request = WebJobRequest(source=source)

    assert request.clips == "auto"
    assert request.to_config().clips == "auto"
    assert request.ranker == "ollama"
    assert request.to_config().ranker == "ollama"
    assert request.to_config().ollama_model == "qwen3:1.7b"
    assert request.caption_style == "bold"
    assert request.to_config().playback_speed == 1.1


def test_batch_preserves_subfolders_to_avoid_duplicate_episode_name_collisions(
    tmp_path: Path,
) -> None:
    library = tmp_path / "Show"
    for season in ("Season 01", "Season 02"):
        folder = library / season
        folder.mkdir(parents=True)
        (folder / "Episode 01.mkv").touch()
    output = tmp_path / "Downloads" / "MediaViralClipper"

    jobs = WebBatchRequest(source=library, output=output).to_jobs()

    assert [job.output for job in jobs] == [output / "Season 01", output / "Season 02"]


def test_job_completes_with_monotonic_pipeline_progress(tmp_path: Path) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"media")

    class FakePipeline:
        def __init__(self, config: ClipperConfig, progress: object) -> None:
            self.config = config
            self.progress = progress

        def run(self, path: Path, dry_run: bool) -> PipelineResult:
            self.progress(Stage.PROBE, StageStatus.COMPLETED, "Media inspected")  # type: ignore[operator]
            self.progress(Stage.TRANSCRIPT, StageStatus.COMPLETED, "Dialogue ready")  # type: ignore[operator]
            self.progress(Stage.RANKING, StageStatus.COMPLETED, "Moments ranked")  # type: ignore[operator]
            return PipelineResult(
                source=path,
                episode_directory=self.config.output / "episode",
                dry_run=dry_run,
                selections=(_selection(),),
            )

    manager = JobManager(pipeline_factory=FakePipeline)
    job_id = manager.start(WebJobRequest(source=source, output=tmp_path / "output", dry_run=True))
    snapshot = manager.wait(job_id, timeout=2)
    manager.close()

    assert snapshot.status == "completed"
    assert snapshot.progress == 100
    assert snapshot.output_directory == tmp_path / "output" / "episode"
    assert snapshot.selections[0].score.overall == 0.85
    progress = [event.progress for event in snapshot.events]
    assert progress == sorted(progress)
    assert {event.stage for event in snapshot.events} >= {"probe", "transcript", "ranking"}


def test_pipeline_failure_becomes_readable_failed_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "broken.mkv"
    source.write_bytes(b"media")

    class FailingPipeline:
        def __init__(self, config: ClipperConfig, progress: object) -> None:
            del config, progress

        def run(self, path: Path, dry_run: bool) -> PipelineResult:
            del path, dry_run
            raise RuntimeError("No dialogue was detected")

    manager = JobManager(pipeline_factory=FailingPipeline)
    job_id = manager.start(WebJobRequest(source=source, output=tmp_path / "output"))
    snapshot = manager.wait(job_id, timeout=2)
    manager.close()

    assert snapshot.status == "failed"
    assert snapshot.error == "No dialogue was detected"
    assert snapshot.finished_at is not None


def test_single_worker_leaves_second_job_queued(tmp_path: Path) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"media")
    release_at = time.monotonic() + 0.15

    class SlowPipeline:
        def __init__(self, config: ClipperConfig, progress: object) -> None:
            self.config = config

        def run(self, path: Path, dry_run: bool) -> PipelineResult:
            while time.monotonic() < release_at:
                time.sleep(0.01)
            return PipelineResult(
                source=path,
                episode_directory=self.config.output / "episode",
                dry_run=dry_run,
                selections=(),
            )

    manager = JobManager(pipeline_factory=SlowPipeline, max_workers=1)
    first = manager.start(WebJobRequest(source=source, output=tmp_path / "one"))
    second = manager.start(WebJobRequest(source=source, output=tmp_path / "two"))

    assert manager.get(second).status == "queued"
    assert manager.wait(first, timeout=2).status == "completed"
    assert manager.wait(second, timeout=2).status == "completed"
    manager.close()


def test_batch_groups_sequential_episode_jobs_and_aggregate_progress(tmp_path: Path) -> None:
    library = tmp_path / "Episodes"
    library.mkdir()
    for name in ("02.mkv", "01.mkv", "03.mkv"):
        (library / name).write_bytes(b"media")

    class FakePipeline:
        def __init__(self, config: ClipperConfig, progress: object) -> None:
            self.config = config

        def run(self, path: Path, dry_run: bool) -> PipelineResult:
            return PipelineResult(
                source=path,
                episode_directory=self.config.output / path.stem,
                dry_run=dry_run,
                selections=(),
            )

    manager = JobManager(pipeline_factory=FakePipeline, max_workers=1)
    batch_id = manager.start_batch(WebBatchRequest(source=library, dry_run=True))
    created = manager.get_batch(batch_id)
    for job in created.jobs:
        manager.wait(job.id, timeout=2)
    finished = manager.get_batch(batch_id)
    manager.close()

    assert [job.source.name for job in finished.jobs] == ["01.mkv", "02.mkv", "03.mkv"]
    assert finished.total == 3
    assert finished.completed == 3
    assert finished.failed == 0
    assert finished.progress == 100
    assert finished.status == "completed"


def test_manager_clears_stale_cache_before_work_and_new_cache_when_closed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"media")
    output = tmp_path / "output"
    cache = output / "episode" / ".cache"
    cache.mkdir(parents=True)
    (cache / "stale.json").write_text("old")
    saw_stale_cache: list[bool] = []

    class CachingPipeline:
        def __init__(self, config: ClipperConfig, progress: object) -> None:
            self.config = config

        def run(self, path: Path, dry_run: bool) -> PipelineResult:
            saw_stale_cache.append(cache.exists())
            cache.mkdir(parents=True)
            (cache / "new.json").write_text("new")
            export = output / "episode" / "clip_01" / "vertical.mp4"
            export.parent.mkdir()
            export.write_bytes(b"finished")
            return PipelineResult(
                source=path,
                episode_directory=output / "episode",
                dry_run=dry_run,
                selections=(),
            )

    manager = JobManager(pipeline_factory=CachingPipeline)
    job_id = manager.start(WebJobRequest(source=source, output=output))
    manager.wait(job_id, timeout=2)

    assert saw_stale_cache == [False]
    assert cache.is_dir()
    manager.close()
    assert not cache.exists()
    assert (output / "episode" / "clip_01" / "vertical.mp4").read_bytes() == b"finished"
