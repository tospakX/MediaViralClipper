from pathlib import Path
from types import SimpleNamespace

from clipper.doctor import inspect_system


def test_doctor_distinguishes_required_tools_from_optional_acceleration() -> None:
    available = {"ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"}

    def runner(arguments: list[str]) -> str:
        if "-filters" in arguments:
            return "subtitles V->V Render text subtitles onto input video using libass"
        if "-encoders" in arguments:
            return "libx264"
        return ""

    report = inspect_system(
        which=lambda name: available.get(name),
        runner=runner,
        module_available=lambda name: name in {"faster_whisper", "scenedetect", "cv2"},
        disk_usage=lambda path: SimpleNamespace(free=20 * 1024**3),
        cwd=Path("/tmp"),
    )

    assert report.ready is True
    checks = {check.name: check for check in report.checks}
    assert checks["NVENC"].ok is False
    assert checks["NVENC"].required is False
    assert checks["faster-whisper"].ok is True


def test_doctor_marks_missing_required_binary_as_not_ready() -> None:
    report = inspect_system(
        which=lambda name: None,
        runner=lambda arguments: "",
        module_available=lambda name: True,
        disk_usage=lambda path: SimpleNamespace(free=20 * 1024**3),
        cwd=Path("/tmp"),
    )

    assert report.ready is False
    assert any(check.name == "FFmpeg" and not check.ok for check in report.checks)
