import json
from pathlib import Path

from clipper.media import parse_probe, probe_media

PROBE = {
    "format": {"duration": "120.500"},
    "streams": [
        {
            "index": 0,
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "avg_frame_rate": "24000/1001",
        },
        {"index": 1, "codec_type": "audio", "codec_name": "aac"},
        {
            "index": 3,
            "codec_type": "subtitle",
            "codec_name": "subrip",
            "tags": {"language": "eng", "title": "English dialogue"},
            "disposition": {"default": 1, "forced": 0},
        },
    ],
}


def test_probe_parser_preserves_stream_contract(tmp_path: Path) -> None:
    source = tmp_path / "show #1.mkv"
    source.touch()

    media = parse_probe(source, PROBE)

    assert media.duration == 120.5
    assert media.fps == 24000 / 1001
    assert media.subtitle_streams == (3,)
    assert media.subtitle_tracks[0].language == "eng"
    assert media.subtitle_tracks[0].title == "English dialogue"
    assert media.subtitle_tracks[0].default is True
    assert media.subtitle_tracks[0].forced is False


def test_probe_uses_argv_without_shell_expansion(tmp_path: Path) -> None:
    source = tmp_path / "show $(touch nope).mkv"
    source.touch()
    seen: list[str] = []

    def runner(arguments: list[str]) -> str:
        seen.extend(arguments)
        return json.dumps(PROBE)

    probe_media(source, runner=runner)

    assert seen[-1] == str(source)
    assert seen[0] == "ffprobe"
    assert not (tmp_path / "nope").exists()
