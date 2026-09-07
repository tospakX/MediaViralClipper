"""Run-state contract used by progress displays and structured logs."""

from enum import StrEnum


class Stage(StrEnum):
    PROBE = "probe"
    TRANSCRIPT = "transcript"
    SCENES = "scenes"
    AUDIO = "audio"
    CANDIDATES = "candidates"
    RANKING = "ranking"
    REFINEMENT = "refinement"
    RENDER = "render"


class StageStatus(StrEnum):
    STARTED = "started"
    CACHED = "cached"
    COMPLETED = "completed"
    FAILED = "failed"
