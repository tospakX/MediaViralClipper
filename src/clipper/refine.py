"""Sentence- and pause-safe clip boundary refinement."""

from clipper.config import ClipperConfig
from clipper.models import Candidate, TranscriptSegment


def refine_candidate(
    candidate: Candidate,
    transcript: list[TranscriptSegment],
    config: ClipperConfig,
    media_duration: float,
) -> Candidate:
    indices = list(candidate.segment_indices)
    if not indices:
        indices = [
            index
            for index, segment in enumerate(transcript)
            if segment.end > candidate.start and segment.start < candidate.end
        ]
    if not indices:
        return candidate
    left, right = min(indices), max(indices)
    options: list[tuple[float, int, int]] = []
    for start_index in range(max(0, left - 2), left + 1):
        for end_index in range(right, min(len(transcript), right + 3)):
            start = transcript[start_index].start
            end = transcript[end_index].end
            duration = end - start
            if duration > config.max_duration or end > media_duration:
                continue
            context_bonus = (left - start_index) * 0.45 + (end_index - right) * 0.7
            target_cost = abs(duration - config.target_duration) / config.target_duration
            minimum_cost = 1.5 if duration < config.min_duration else 0.0
            options.append((target_cost + minimum_cost - context_bonus, start_index, end_index))
    if not options:
        start_index, end_index = _fit_hard_cap(transcript, left, right, config.max_duration)
    else:
        _cost, start_index, end_index = min(options, key=lambda item: (item[0], item[1], item[2]))
    selected = transcript[start_index : end_index + 1]
    return candidate.model_copy(
        update={
            "start": selected[0].start,
            "end": min(selected[-1].end, media_duration),
            "transcript": " ".join(segment.text.strip() for segment in selected),
            "segment_indices": tuple(range(start_index, end_index + 1)),
        }
    )


def _fit_hard_cap(
    transcript: list[TranscriptSegment], left: int, right: int, hard_cap: float
) -> tuple[int, int]:
    while transcript[right].end - transcript[left].start > hard_cap and left < right:
        left_context = transcript[left + 1].start - transcript[left].start
        right_context = transcript[right].end - transcript[right - 1].end
        if left_context >= right_context:
            left += 1
        else:
            right -= 1
    return left, right
