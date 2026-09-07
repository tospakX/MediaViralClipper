"""FFmpeg command construction and isolated clip rendering."""

from collections.abc import Callable
from pathlib import Path

from clipper.process import CommandError, run_command, run_streaming
from clipper.reframe import crop_dimensions


def build_original_command(
    source: Path,
    destination: Path,
    start: float,
    end: float,
    encoder: str = "libx264",
    subtitle_path: Path | None = None,
    threads: int = 2,
    playback_speed: float = 1.1,
) -> list[str]:
    filters = [f"setpts=PTS/{playback_speed:.4f}"]
    if subtitle_path:
        filters.append(f"subtitles='{_filter_escape(subtitle_path)}'")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{end - start:.3f}",
        "-i",
        str(source),
    ]
    if filters:
        command.extend(["-vf", ",".join(filters)])
    command.extend(_encoding_arguments(encoder, threads))
    command.extend(
        [
            "-filter:a",
            f"atempo={playback_speed:.4f}",
            "-c:a",
            "aac",
            "-q:a",
            "2",
            "-movflags",
            "+faststart",
            str(destination),
        ]
    )
    return command


def build_vertical_filter(
    source_width: int,
    source_height: int,
    crop_x_expression: str,
    subtitle_path: Path | None,
    playback_speed: float = 1.1,
) -> str:
    crop_width, crop_height = crop_dimensions(source_width, source_height)
    filters = [
        f"crop={crop_width}:{crop_height}:x='{crop_x_expression}':y=0",
        "scale=1080:1920:flags=lanczos",
        "setsar=1",
        f"setpts=PTS/{playback_speed:.4f}",
    ]
    if subtitle_path:
        filters.append(f"ass='{_filter_escape(subtitle_path)}'")
    return ",".join(filters)


def build_vertical_command(
    source: Path,
    destination: Path,
    start: float,
    end: float,
    width: int,
    height: int,
    crop_x_expression: str,
    encoder: str = "libx264",
    subtitle_path: Path | None = None,
    threads: int = 2,
    playback_speed: float = 1.1,
) -> list[str]:
    return [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{end - start:.3f}",
        "-i",
        str(source),
        "-vf",
        build_vertical_filter(width, height, crop_x_expression, subtitle_path, playback_speed),
        *_encoding_arguments(encoder, threads),
        "-filter:a",
        f"atempo={playback_speed:.4f}",
        "-c:a",
        "aac",
        "-q:a",
        "2",
        "-movflags",
        "+faststart",
        str(destination),
    ]


def available_encoder(preference: str = "auto") -> str:
    if preference == "cpu":
        return "libx264"
    encoders = run_command(["ffmpeg", "-hide_banner", "-encoders"])
    has_nvenc = "h264_nvenc" in encoders
    if preference == "nvenc" and not has_nvenc:
        raise RuntimeError("NVENC requested but h264_nvenc is unavailable")
    return "h264_nvenc" if has_nvenc else "libx264"


def render_command(arguments: list[str]) -> None:
    Path(arguments[-1]).parent.mkdir(parents=True, exist_ok=True)
    run_streaming(arguments)


def render_with_fallback(
    preferred_command: list[str],
    cpu_command: list[str],
    runner: Callable[[list[str]], None] = render_command,
) -> str:
    try:
        runner(preferred_command)
        return "h264_nvenc" if "h264_nvenc" in preferred_command else "libx264"
    except CommandError:
        if "h264_nvenc" not in preferred_command:
            raise
        runner(cpu_command)
        return "libx264"


def _encoding_arguments(encoder: str, threads: int) -> list[str]:
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "p5", "-cq", "20", "-pix_fmt", "yuv420p"]
    return [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-threads",
        str(threads),
        "-pix_fmt",
        "yuv420p",
    ]


def _filter_escape(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", r"'\\''")
