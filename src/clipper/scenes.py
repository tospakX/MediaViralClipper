"""Scene boundary detection with an optional PySceneDetect backend."""

from collections.abc import Callable
from itertools import pairwise
from pathlib import Path

from clipper.models import Scene


def normalize_scene_cuts(
    cuts: list[float], duration: float, minimum_scene: float = 0.35
) -> list[Scene]:
    boundaries = sorted({max(0.0, min(duration, value)) for value in [0.0, *cuts, duration]})
    merged = [boundaries[0]]
    for boundary in boundaries[1:-1]:
        if boundary - merged[-1] >= minimum_scene:
            merged.append(boundary)
    if duration - merged[-1] < minimum_scene and len(merged) > 1:
        merged.pop()
    merged.append(duration)
    return [Scene(start=start, end=end) for start, end in pairwise(merged) if end > start]


def detect_scenes(
    source: Path,
    duration: float,
    threshold: float = 27.0,
    backend: Callable[[Path, float], list[float]] | None = None,
) -> list[Scene]:
    detector = backend or _scenedetect_cuts
    try:
        cuts = detector(source, threshold)
    except Exception:
        return _fallback_scenes(duration)
    return normalize_scene_cuts(cuts, duration)


def _scenedetect_cuts(source: Path, threshold: float) -> list[float]:
    from scenedetect import ContentDetector, detect

    detected = detect(str(source), ContentDetector(threshold=threshold), show_progress=False)
    cuts = [start.get_seconds() for start, _end in detected]
    cuts.extend(end.get_seconds() for _start, end in detected)
    return cuts


def _fallback_scenes(duration: float, interval: float = 30.0) -> list[Scene]:
    return normalize_scene_cuts(
        [float(value) for value in range(int(interval), int(duration), int(interval))], duration
    )
