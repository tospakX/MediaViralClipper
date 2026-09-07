"""Low-rate audio energy analysis for silence, reactions, and pacing signals."""

from collections.abc import Callable
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from clipper.models import AudioInterval
from clipper.process import CommandError, run_binary


def intervals_from_samples(
    samples: NDArray[np.float32], sample_rate: int, window_seconds: float = 0.5
) -> list[AudioInterval]:
    window = max(1, round(sample_rate * window_seconds))
    intervals: list[AudioInterval] = []
    for offset in range(0, len(samples), window):
        chunk = samples[offset : offset + window]
        if not len(chunk):
            continue
        rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float64)))))
        peak = float(np.max(np.abs(chunk)))
        intervals.append(
            AudioInterval(
                start=offset / sample_rate,
                end=(offset + len(chunk)) / sample_rate,
                rms=max(0.0, rms),
                peak=max(0.0, peak),
            )
        )
    return intervals


def analyze_audio(
    source: Path,
    sample_rate: int = 8000,
    runner: Callable[[list[str]], bytes] = run_binary,
) -> list[AudioInterval]:
    arguments = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "-",
    ]
    try:
        raw_audio = runner(arguments)
    except CommandError as error:
        missing_stream_messages = (
            "does not contain any stream",
            "matches no streams",
            "stream map '0:a' matches no streams",
        )
        if any(message in error.stderr.lower() for message in missing_stream_messages):
            return []
        raise
    samples = np.frombuffer(raw_audio, dtype="<f4")
    return intervals_from_samples(samples, sample_rate)
