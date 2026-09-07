"""Serializable contracts shared between pipeline stages."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SubtitleTrack(FrozenModel):
    index: int = Field(ge=0)
    codec: str = "unknown"
    language: str | None = None
    title: str | None = None
    default: bool = False
    forced: bool = False


class MediaInfo(FrozenModel):
    source: Path
    duration: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    video_codec: str
    audio_codec: str | None = None
    subtitle_streams: tuple[int, ...] = ()
    subtitle_tracks: tuple[SubtitleTrack, ...] = ()


class Word(FrozenModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str
    probability: float | None = None


class TranscriptSegment(FrozenModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str
    words: tuple[Word, ...] = ()
    speaker: str | None = None


class Scene(FrozenModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    score: float = Field(default=0, ge=0)


class AudioInterval(FrozenModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    rms: float = Field(ge=0)
    peak: float = Field(ge=0)


class Candidate(FrozenModel):
    id: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    transcript: str
    segment_indices: tuple[int, ...]
    features: dict[str, float] = {}

    @property
    def duration(self) -> float:
        return self.end - self.start


class Score(FrozenModel):
    humor: float = Field(ge=0, le=1)
    punchline: float = Field(ge=0, le=1)
    surprise: float = Field(ge=0, le=1)
    quotability: float = Field(ge=0, le=1)
    hook: float = Field(ge=0, le=1)
    standalone: float = Field(ge=0, le=1)
    pacing: float = Field(ge=0, le=1)
    reaction: float = Field(ge=0, le=1)
    retention: float = Field(ge=0, le=1)
    overall: float = Field(ge=0, le=1)
    explanation: str


class RankedCandidate(FrozenModel):
    candidate: Candidate
    score: Score


class Selection(FrozenModel):
    rank: int = Field(ge=1)
    candidate: Candidate
    score: Score


class RenderResult(FrozenModel):
    clip: int
    original: Path | None = None
    vertical: Path | None = None
    subtitles: Path | None = None
    error: str | None = None
