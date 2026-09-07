import json
from dataclasses import dataclass
from pathlib import Path

from clipper.config import ClipperConfig
from clipper.models import AudioInterval, MediaInfo, Scene, TranscriptSegment
from clipper.pipeline import ClipperPipeline, PipelineServices
from clipper.state import Stage, StageStatus


@dataclass
class Calls:
    probe: int = 0
    transcript: int = 0
    scenes: int = 0
    audio: int = 0


def _services(calls: Calls) -> PipelineServices:
    dialogue = [
        TranscriptSegment(start=1, end=5, text="Wait, the robot is our new lawyer?"),
        TranscriptSegment(start=5.5, end=9, text="It passed the bar exam."),
        TranscriptSegment(start=10, end=14, text="Robots can take the bar?"),
        TranscriptSegment(start=14.5, end=18, text="No, it physically lifted the bar."),
        TranscriptSegment(start=19, end=22, text="That explains the dents!"),
    ]

    def probe(source: Path) -> MediaInfo:
        calls.probe += 1
        return MediaInfo(
            source=source,
            duration=25,
            width=320,
            height=180,
            fps=10,
            video_codec="h264",
            audio_codec="aac",
        )

    def transcript(
        source: Path, media: MediaInfo, config: ClipperConfig
    ) -> list[TranscriptSegment]:
        calls.transcript += 1
        return dialogue

    def scenes(source: Path, duration: float, threshold: float) -> list[Scene]:
        calls.scenes += 1
        return [Scene(start=0, end=duration)]

    def audio(source: Path) -> list[AudioInterval]:
        calls.audio += 1
        return [AudioInterval(start=0, end=25, rms=0.2, peak=0.5)]

    return PipelineServices(probe=probe, transcribe=transcript, scenes=scenes, audio=audio)


def test_dry_run_writes_rankings_but_does_not_render(tmp_path: Path) -> None:
    source = tmp_path / "Episode With Spaces.mkv"
    source.write_bytes(b"fixture")
    calls = Calls()
    config = ClipperConfig(
        output=tmp_path / "output",
        clips=2,
        min_duration=10,
        max_duration=23,
        target_duration=18,
    )

    result = ClipperPipeline(config, _services(calls)).run(source, dry_run=True)

    assert result.dry_run is True
    assert result.episode_directory.name == "Episode_With_Spaces"
    assert (result.episode_directory / "ranking.json").is_file()
    assert (result.episode_directory / "transcript.json").is_file()
    assert not list(result.episode_directory.glob("clip_*"))
    assert result.selections


def test_second_dry_run_reuses_every_expensive_stage(tmp_path: Path) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"fixture")
    calls = Calls()
    config = ClipperConfig(
        output=tmp_path / "output",
        min_duration=10,
        max_duration=23,
        target_duration=18,
    )
    pipeline = ClipperPipeline(config, _services(calls))

    first = pipeline.run(source, dry_run=True)
    second = pipeline.run(source, dry_run=True)

    assert first.selections == second.selections
    assert calls == Calls(probe=1, transcript=1, scenes=1, audio=1)


def test_render_only_settings_do_not_invalidate_candidate_cache(tmp_path: Path) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"fixture")
    common = dict(
        output=tmp_path / "output",
        min_duration=10,
        max_duration=23,
        target_duration=18,
    )

    first = ClipperPipeline(ClipperConfig(**common, vertical=False), _services(Calls())).run(
        source, dry_run=True
    )
    cache_path = first.episode_directory / ".cache" / "candidates.json"
    first_key = json.loads(cache_path.read_text(encoding="utf-8"))["fingerprint"]
    ClipperPipeline(ClipperConfig(**common, vertical=True), _services(Calls())).run(
        source, dry_run=True
    )
    second_key = json.loads(cache_path.read_text(encoding="utf-8"))["fingerprint"]

    assert first_key == second_key


def test_structured_log_records_each_pipeline_stage(tmp_path: Path) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"fixture")
    config = ClipperConfig(
        output=tmp_path / "output",
        min_duration=10,
        max_duration=23,
        target_duration=18,
    )

    result = ClipperPipeline(config, _services(Calls())).run(source, dry_run=True)
    events = [
        json.loads(line)
        for line in (result.episode_directory / "run.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert {event["stage"] for event in events} >= {
        "probe",
        "transcript",
        "scenes",
        "audio",
        "candidates",
        "ranking",
        "refinement",
    }


def test_media_without_audio_skips_audio_decoder(tmp_path: Path) -> None:
    source = tmp_path / "silent.mkv"
    source.write_bytes(b"fixture")
    services = _services(Calls())
    original_probe = services.probe

    def silent_probe(path: Path) -> MediaInfo:
        return original_probe(path).model_copy(update={"audio_codec": None})

    def audio_must_not_run(path: Path) -> list[AudioInterval]:
        raise AssertionError(f"audio decoder unexpectedly called for {path}")

    silent_services = PipelineServices(
        probe=silent_probe,
        transcribe=services.transcribe,
        scenes=services.scenes,
        audio=audio_must_not_run,
    )
    config = ClipperConfig(
        output=tmp_path / "output",
        min_duration=10,
        max_duration=23,
        target_duration=18,
    )

    result = ClipperPipeline(config, silent_services).run(source, dry_run=True)

    assert result.selections


def test_one_render_failure_does_not_prevent_later_clips(
    tmp_path: Path, monkeypatch: object
) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"fixture")
    config = ClipperConfig(
        output=tmp_path / "output",
        clips=2,
        min_duration=10,
        max_duration=15,
        target_duration=12,
        vertical=False,
        captions=False,
        hardware_encoding="cpu",
    )
    attempts = 0

    def fake_render(arguments: list[str]) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("synthetic encoder failure")
        Path(arguments[-1]).write_bytes(b"rendered")

    def fake_with_fallback(preferred: list[str], cpu: list[str], runner: object = None) -> str:
        del cpu, runner
        fake_render(preferred)
        return "libx264"

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "clipper.pipeline.render_with_fallback", fake_with_fallback
    )
    result = ClipperPipeline(config, _services(Calls())).run(source)

    assert len(result.renders) == 2
    assert result.renders[0].error == "synthetic encoder failure"
    assert result.renders[1].error is None
    assert (result.episode_directory / "clip_01" / "metadata.json").is_file()
    assert (result.episode_directory / "clip_02" / "metadata.json").is_file()


def test_completed_render_is_reused_on_resume(tmp_path: Path, monkeypatch: object) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"fixture")
    config = ClipperConfig(
        output=tmp_path / "output",
        clips=1,
        min_duration=10,
        max_duration=15,
        target_duration=12,
        vertical=False,
        captions=False,
        hardware_encoding="cpu",
    )
    attempts = 0

    def fake_with_fallback(preferred: list[str], cpu: list[str], runner: object = None) -> str:
        nonlocal attempts
        del cpu, runner
        attempts += 1
        Path(preferred[-1]).write_bytes(b"rendered")
        return "libx264"

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "clipper.pipeline.render_with_fallback", fake_with_fallback
    )
    pipeline = ClipperPipeline(config, _services(Calls()))

    first = pipeline.run(source)
    second = pipeline.run(source)

    assert first.renders == second.renders
    assert attempts == 1


def test_encoder_capability_is_detected_once_per_run(tmp_path: Path, monkeypatch: object) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"fixture")
    detections = 0

    def fake_encoder(preference: str) -> str:
        nonlocal detections
        detections += 1
        return "libx264"

    def fake_render(preferred: list[str], cpu: list[str], runner: object = None) -> str:
        del cpu, runner
        Path(preferred[-1]).write_bytes(b"rendered")
        return "libx264"

    monkeypatch.setattr("clipper.pipeline.available_encoder", fake_encoder)  # type: ignore[attr-defined]
    monkeypatch.setattr("clipper.pipeline.render_with_fallback", fake_render)  # type: ignore[attr-defined]
    config = ClipperConfig(
        output=tmp_path / "output",
        clips=2,
        min_duration=10,
        max_duration=15,
        target_duration=12,
        vertical=False,
        captions=False,
    )

    result = ClipperPipeline(config, _services(Calls())).run(source)

    assert len(result.renders) == 2
    assert detections == 1


def test_render_reports_started_before_completion(tmp_path: Path, monkeypatch: object) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"fixture")
    events: list[tuple[Stage, StageStatus]] = []

    def fake_render(preferred: list[str], cpu: list[str], runner: object = None) -> str:
        del cpu, runner
        Path(preferred[-1]).write_bytes(b"rendered")
        return "libx264"

    monkeypatch.setattr("clipper.pipeline.render_with_fallback", fake_render)  # type: ignore[attr-defined]
    config = ClipperConfig(
        output=tmp_path / "output",
        clips=1,
        min_duration=10,
        max_duration=15,
        target_duration=12,
        vertical=False,
        captions=False,
        hardware_encoding="cpu",
    )
    ClipperPipeline(
        config,
        _services(Calls()),
        progress=lambda stage, status, _message: events.append((stage, status)),
    ).run(source)

    render_events = [status for stage, status in events if stage == Stage.RENDER]
    assert render_events == [StageStatus.STARTED, StageStatus.COMPLETED]


def test_rerender_with_fewer_selections_removes_stale_generated_clip_directory(
    tmp_path: Path, monkeypatch: object
) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"fixture")
    output = tmp_path / "output"

    def fake_render(preferred: list[str], cpu: list[str], runner: object = None) -> str:
        del cpu, runner
        Path(preferred[-1]).write_bytes(b"rendered")
        return "libx264"

    monkeypatch.setattr("clipper.pipeline.render_with_fallback", fake_render)  # type: ignore[attr-defined]
    common = dict(
        output=output,
        min_duration=10,
        max_duration=15,
        target_duration=12,
        vertical=False,
        captions=False,
        hardware_encoding="cpu",
    )
    first = ClipperPipeline(ClipperConfig(**common, clips=2), _services(Calls())).run(source)
    assert (first.episode_directory / "clip_02" / "metadata.json").is_file()

    second = ClipperPipeline(
        ClipperConfig(**common, clips=1, overwrite=True), _services(Calls())
    ).run(source)

    assert (second.episode_directory / "clip_01" / "metadata.json").is_file()
    assert not (second.episode_directory / "clip_02").exists()
