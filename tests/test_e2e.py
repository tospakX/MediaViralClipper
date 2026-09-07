import json
import shutil
import subprocess
from pathlib import Path

import pytest

from clipper.config import ClipperConfig
from clipper.pipeline import ClipperPipeline


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is required")
def test_synthetic_media_dry_run_and_vertical_render(tmp_path: Path) -> None:
    source = tmp_path / "Synthetic Comedy.mkv"
    subtitles = Path(__file__).parent / "fixtures" / "transcript.srt"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=10:duration=12",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000:duration=12",
            "-i",
            str(subtitles),
            "-map",
            "0:v",
            "-map",
            "1:a",
            "-map",
            "2:s",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-c:s",
            "srt",
            str(source),
        ],
        check=True,
    )
    config = ClipperConfig(
        output=tmp_path / "output",
        clips=1,
        min_duration=4,
        max_duration=9,
        target_duration=7,
        vertical=True,
        captions=True,
        hardware_encoding="cpu",
    )
    pipeline = ClipperPipeline(config)

    dry = pipeline.run(source, dry_run=True)
    rendered = pipeline.run(source, dry_run=False)

    assert dry.selections == rendered.selections
    clip_directory = rendered.episode_directory / "clip_01"
    assert (clip_directory / "original.mp4").is_file()
    assert (clip_directory / "vertical.mp4").is_file()
    assert (clip_directory / "subtitles.srt").is_file()
    metadata = json.loads((clip_directory / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["duration"] <= 9
    assert set(("humor", "hook", "standalone", "overall", "explanation")) <= metadata.keys()
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(clip_directory / "vertical.mp4"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert (stream["width"], stream["height"]) == (1080, 1920)
