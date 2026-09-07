"""Dialogue-led generation of many coherent candidate windows."""

import re

from clipper.cache import fingerprint
from clipper.config import ClipperConfig
from clipper.models import AudioInterval, Candidate, Scene, TranscriptSegment

_FILLER = re.compile(r"\b(previously on|opening theme|subtitles by|directed by|credits)\b", re.I)


def generate_candidates(
    transcript: list[TranscriptSegment],
    scenes: list[Scene],
    config: ClipperConfig,
    media_duration: float,
    audio: list[AudioInterval] | None = None,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen: set[tuple[int, int]] = set()
    for left, first in enumerate(transcript):
        if (
            _FILLER.search(first.text)
            or first.start < min(3.0, media_duration * 0.002)
            or not _safe_start(first.text)
        ):
            continue
        for right in range(left, len(transcript)):
            last = transcript[right]
            duration = last.end - first.start
            if duration > config.max_duration:
                break
            if duration < config.min_duration:
                continue
            if not _sentence_complete(last.text):
                continue
            key = (left, right)
            if key in seen:
                continue
            seen.add(key)
            text = " ".join(segment.text.strip() for segment in transcript[left : right + 1])
            pauses = [
                max(0.0, transcript[index + 1].start - transcript[index].end)
                for index in range(left, right)
            ]
            identifier = fingerprint(
                {"start": round(first.start, 3), "end": round(last.end, 3), "text": text}
            )[:12]
            matching_audio = [
                interval
                for interval in (audio or [])
                if interval.end > first.start and interval.start < last.end
            ]
            candidates.append(
                Candidate(
                    id=identifier,
                    start=first.start,
                    end=min(last.end, media_duration),
                    transcript=text,
                    segment_indices=tuple(range(left, right + 1)),
                    features={
                        "dialogue_density": min(1.0, len(text.split()) / max(1.0, duration * 2.5)),
                        "pause_mean": sum(pauses) / len(pauses) if pauses else 0.0,
                        "target_fit": 1
                        - min(1.0, abs(duration - config.target_duration) / config.target_duration),
                        "scene_changes": float(
                            sum(first.start < scene.start < last.end for scene in scenes)
                        ),
                        "audio_rms": round(
                            sum(item.rms for item in matching_audio) / len(matching_audio), 4
                        )
                        if matching_audio
                        else 0.0,
                        "audio_peak": max((item.peak for item in matching_audio), default=0.0),
                    },
                )
            )
    return sorted(candidates, key=lambda item: (item.start, item.end, item.id))


def _sentence_complete(text: str) -> bool:
    return text.rstrip().endswith((".", "?", "!", "…", ".”", "!”", "?“", '?"'))


def _safe_start(text: str) -> bool:
    first = next((character for character in text.lstrip() if character.isalpha()), "")
    return not first or not first.islower()
