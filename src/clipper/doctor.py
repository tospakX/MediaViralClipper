"""Read-only readiness checks for running a full episode locally."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from clipper.process import CommandError, run_command


class SystemCheck(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    ok: bool
    required: bool
    detail: str


class SystemReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    ready: bool
    checks: tuple[SystemCheck, ...]
    summary: str


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def inspect_system(
    *,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[[list[str]], str] = run_command,
    module_available: Callable[[str], bool] | None = None,
    disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    cwd: Path | None = None,
) -> SystemReport:
    """Inspect dependencies without downloading models or changing the machine."""
    if module_available is None:
        module_available = _module_available
    checks: list[SystemCheck] = []
    ffmpeg = which("ffmpeg")
    ffprobe = which("ffprobe")
    checks.append(
        SystemCheck(name="FFmpeg", ok=bool(ffmpeg), required=True, detail=ffmpeg or "not on PATH")
    )
    checks.append(
        SystemCheck(
            name="ffprobe", ok=bool(ffprobe), required=True, detail=ffprobe or "not on PATH"
        )
    )

    filters = _safe_command(runner, ["ffmpeg", "-hide_banner", "-filters"]) if ffmpeg else ""
    encoders = _safe_command(runner, ["ffmpeg", "-hide_banner", "-encoders"]) if ffmpeg else ""
    has_subtitles = "subtitles" in filters and "libass" in filters.lower()
    checks.append(
        SystemCheck(
            name="Burned captions",
            ok=has_subtitles,
            required=True,
            detail="FFmpeg libass filter available"
            if has_subtitles
            else "FFmpeg subtitles/libass filter missing",
        )
    )
    checks.append(
        SystemCheck(
            name="NVENC",
            ok="h264_nvenc" in encoders,
            required=False,
            detail="hardware H.264 available"
            if "h264_nvenc" in encoders
            else "optional; CPU encoding will be used",
        )
    )

    ollama = which("ollama")
    ollama_models = _safe_command(runner, ["ollama", "list"]) if ollama else ""
    qwen_ready = "qwen3:1.7b" in ollama_models
    checks.append(
        SystemCheck(
            name="Ollama · qwen3:1.7b",
            ok=qwen_ready,
            required=False,
            detail=(
                "local Qwen moment judge ready"
                if qwen_ready
                else "optional; fast heuristic fallback will be used"
            ),
        )
    )

    for module, label, required in (
        ("faster_whisper", "faster-whisper", True),
        ("scenedetect", "PySceneDetect", False),
        ("cv2", "OpenCV", False),
    ):
        present = module_available(module)
        checks.append(
            SystemCheck(
                name=label,
                ok=present,
                required=required,
                detail="installed"
                if present
                else ("missing" if required else "optional fallback available"),
            )
        )

    free_bytes = int(disk_usage(cwd or Path.cwd()).free)
    enough_disk = free_bytes >= 2 * 1024**3
    checks.append(
        SystemCheck(
            name="Free disk",
            ok=enough_disk,
            required=True,
            detail=f"{free_bytes / 1024**3:.1f} GiB available",
        )
    )
    ready = all(check.ok for check in checks if check.required)
    return SystemReport(
        ready=ready,
        checks=tuple(checks),
        summary="Ready for an episode" if ready else "Required setup is missing",
    )


def _safe_command(runner: Callable[[list[str]], str], arguments: list[str]) -> str:
    try:
        return runner(arguments)
    except (CommandError, OSError):
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Media Viral Clipper readiness")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    arguments = parser.parse_args()
    report = inspect_system()
    if arguments.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2))
    else:
        marker = "READY" if report.ready else "NOT READY"
        print(f"Media Viral Clipper: {marker} — {report.summary}")
        for check in report.checks:
            symbol = "✓" if check.ok else ("✗" if check.required else "·")
            kind = "required" if check.required else "optional"
            print(f"  {symbol} {check.name}: {check.detail} ({kind})")
    if not report.ready:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
