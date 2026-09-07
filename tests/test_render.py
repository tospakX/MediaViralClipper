from pathlib import Path

from clipper.process import CommandError
from clipper.render import (
    build_original_command,
    build_vertical_command,
    build_vertical_filter,
    render_with_fallback,
)


def test_original_render_command_keeps_special_filename_as_one_argument(tmp_path: Path) -> None:
    source = tmp_path / "show; not a command.mkv"
    destination = tmp_path / "clip one.mp4"

    command = build_original_command(source, destination, start=3.25, end=23.5, encoder="libx264")

    assert str(source) in command
    assert command[-1] == str(destination)
    assert command[command.index("-t") + 1] == "20.250"
    assert command[command.index("-threads") + 1] == "2"
    assert command[command.index("-q:a") + 1] == "2"
    assert "-b:a" not in command
    assert command.index("-t") < command.index("-i")
    assert "setpts=PTS/1.1000" in command[command.index("-vf") + 1]
    assert command[command.index("-filter:a") + 1] == "atempo=1.1000"


def test_vertical_render_uses_quality_based_aac_for_low_bitrate_sources(tmp_path: Path) -> None:
    command = build_vertical_command(
        tmp_path / "source.mkv",
        tmp_path / "vertical.mp4",
        0,
        20,
        1920,
        1080,
        "100",
    )

    assert command[command.index("-q:a") + 1] == "2"
    assert "-b:a" not in command


def test_vertical_filter_outputs_exact_canvas_and_moves_crop() -> None:
    expression = build_vertical_filter(
        source_width=1920,
        source_height=1080,
        crop_x_expression="if(lt(t,1),100,200)",
        subtitle_path=None,
    )

    assert "crop=608:1080" in expression
    assert "scale=1080:1920" in expression
    assert "setsar=1" in expression
    assert "if(lt(t,1),100,200)" in expression


def test_vertical_render_accelerates_video_and_audio_together(tmp_path: Path) -> None:
    command = build_vertical_command(
        tmp_path / "source.mkv",
        tmp_path / "vertical.mp4",
        0,
        22,
        1920,
        1080,
        "100",
    )

    assert command.index("-t") < command.index("-i")
    assert "setpts=PTS/1.1000" in command[command.index("-vf") + 1]
    assert command[command.index("-filter:a") + 1] == "atempo=1.1000"


def test_nvenc_runtime_failure_falls_back_to_cpu() -> None:
    attempts: list[list[str]] = []

    def runner(arguments: list[str]) -> None:
        attempts.append(arguments)
        if "h264_nvenc" in arguments:
            raise CommandError(arguments, 1, "GPU unavailable")

    used = render_with_fallback(
        ["ffmpeg", "-c:v", "h264_nvenc", "gpu.mp4"],
        ["ffmpeg", "-c:v", "libx264", "cpu.mp4"],
        runner=runner,
    )

    assert used == "libx264"
    assert len(attempts) == 2
