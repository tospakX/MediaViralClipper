"""Media probing through ffprobe."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipper.models import MediaInfo, SubtitleTrack
from clipper.process import run_command


def _frame_rate(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 30.0
    numerator, separator, denominator = value.partition("/")
    if not separator:
        return float(numerator)
    return float(numerator) / float(denominator)


def parse_probe(source: Path, payload: dict[str, Any]) -> MediaInfo:
    streams = payload.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"no video stream found in {source}")
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    duration_value = payload.get("format", {}).get("duration") or video.get("duration")
    if duration_value in {None, "N/A"}:
        raise ValueError(f"duration unavailable for {source}")
    subtitle_items = [item for item in streams if item.get("codec_type") == "subtitle"]
    subtitles = tuple(int(item["index"]) for item in subtitle_items)
    subtitle_tracks = tuple(
        SubtitleTrack(
            index=int(item["index"]),
            codec=str(item.get("codec_name", "unknown")),
            language=item.get("tags", {}).get("language"),
            title=item.get("tags", {}).get("title"),
            default=bool(item.get("disposition", {}).get("default", 0)),
            forced=bool(item.get("disposition", {}).get("forced", 0)),
        )
        for item in subtitle_items
    )
    return MediaInfo(
        source=source.resolve(),
        duration=float(duration_value),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=_frame_rate(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        video_codec=str(video.get("codec_name", "unknown")),
        audio_codec=str(audio.get("codec_name")) if audio else None,
        subtitle_streams=subtitles,
        subtitle_tracks=subtitle_tracks,
    )


def probe_media(source: Path, runner: Callable[[list[str]], str] = run_command) -> MediaInfo:
    if not source.is_file():
        raise FileNotFoundError(source)
    arguments = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(source),
    ]
    try:
        payload = json.loads(runner(arguments))
    except json.JSONDecodeError as error:
        raise ValueError(f"ffprobe returned invalid JSON for {source}") from error
    return parse_probe(source, payload)
