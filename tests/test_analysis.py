import numpy as np
import pytest

from clipper.audio import analyze_audio, intervals_from_samples
from clipper.process import CommandError
from clipper.scenes import detect_scenes, normalize_scene_cuts


def test_scene_cuts_include_media_edges_and_drop_micro_scenes() -> None:
    scenes = normalize_scene_cuts([0.0, 0.2, 4.0, 9.5], duration=10.0, minimum_scene=0.5)

    assert [(scene.start, scene.end) for scene in scenes] == [(0.0, 4.0), (4.0, 9.5), (9.5, 10.0)]


def test_audio_intervals_measure_silence_and_energy() -> None:
    samples = np.concatenate([np.zeros(100), np.full(100, 0.5, dtype=np.float32)])

    intervals = intervals_from_samples(samples, sample_rate=100, window_seconds=1.0)

    assert intervals[0].rms == 0
    assert 0.49 < intervals[1].rms < 0.51
    assert intervals[1].peak == 0.5


def test_missing_audio_stream_degrades_to_empty_analysis(tmp_path: object) -> None:
    def no_audio(arguments: list[str]) -> bytes:
        raise CommandError(arguments, 234, "Output file does not contain any stream")

    assert analyze_audio(tmp_path / "silent.mp4", runner=no_audio) == []  # type: ignore[operator]


def test_corrupt_audio_decode_is_not_hidden(tmp_path: object) -> None:
    def corrupt(arguments: list[str]) -> bytes:
        raise CommandError(arguments, 1, "Invalid data found when processing input")

    with pytest.raises(CommandError, match="Invalid data"):
        analyze_audio(tmp_path / "broken.mp4", runner=corrupt)  # type: ignore[operator]


def test_scene_backend_failure_uses_deterministic_fallback(tmp_path: object) -> None:
    def broken_backend(source: object, threshold: float) -> list[float]:
        raise RuntimeError("decoder rejected frame")

    scenes = detect_scenes(
        tmp_path / "episode.mkv",
        65,
        threshold=27,
        backend=broken_backend,  # type: ignore[operator]
    )

    assert [(scene.start, scene.end) for scene in scenes] == [
        (0, 30),
        (30, 60),
        (60, 65),
    ]
