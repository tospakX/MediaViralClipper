"""Deterministic dialogue-aware scoring and diversity selection."""

import math
import re
from collections import Counter

from clipper.models import Candidate, RankedCandidate, Score

_SURPRISE = {"what", "wait", "impossible", "suddenly", "actually", "seriously", "why", "how"}
_HUMOR = {"haha", "ha", "joke", "ridiculous", "idiot", "horse", "pigeon", "weird", "absurd"}
_REACTION = {"wow", "what", "no", "yes", "oh", "whoa", "really", "seriously"}
_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "is", "it", "that", "this"}


class HeuristicRanker:
    """Explainable offline baseline; transcript carries most of the score."""

    def rank(self, candidates: list[Candidate]) -> list[RankedCandidate]:
        ranked = [RankedCandidate(candidate=item, score=self.score(item)) for item in candidates]
        return sorted(ranked, key=lambda item: (-item.score.overall, item.candidate.start))

    def score(self, candidate: Candidate) -> Score:
        text = candidate.transcript.strip()
        words = re.findall(r"[\w']+", text.lower())
        word_set = set(words)
        questions = text.count("?")
        exclamations = text.count("!")
        turns = max(1, text.count(".") + questions + exclamations)
        humor = _cap(0.12 + 0.18 * len(word_set & _HUMOR) + 0.08 * exclamations)
        visual_change = min(1.0, candidate.features.get("scene_changes", 0.0) / 3)
        audio_peak = min(1.0, candidate.features.get("audio_peak", 0.0))
        surprise = _cap(
            0.08 + 0.16 * len(word_set & _SURPRISE) + 0.10 * questions + 0.08 * visual_change
        )
        punchline = _cap(0.12 + 0.20 * exclamations + 0.12 * questions + 0.25 * humor)
        quotability = _cap(0.65 if 4 <= len(words) <= 45 else 0.35)
        hook = _cap(0.15 + 0.20 * bool(word_set & _SURPRISE) + 0.12 * text[:40].count("?"))
        standalone = _cap(0.35 + 0.10 * turns - 0.15 * text.lower().startswith(("and ", "but ")))
        density = candidate.features.get("dialogue_density", min(1.0, len(words) / 50))
        pacing = _cap(
            0.25 + 0.6 * density - 0.1 * max(0.0, candidate.features.get("pause_mean", 0) - 1)
        )
        reaction = _cap(
            0.1 + 0.13 * len(word_set & _REACTION) + 0.08 * exclamations + 0.18 * audio_peak
        )
        retention = _cap(
            0.23 * hook + 0.23 * punchline + 0.22 * pacing + 0.22 * surprise + 0.10 * visual_change
        )
        overall = _cap(
            0.18 * humor
            + 0.16 * punchline
            + 0.10 * surprise
            + 0.08 * quotability
            + 0.14 * hook
            + 0.13 * standalone
            + 0.08 * pacing
            + 0.05 * reaction
            + 0.08 * retention
        )
        strongest = max(
            {"humor": humor, "hook": hook, "punchline": punchline, "surprise": surprise},
            key=lambda name: {
                "humor": humor,
                "hook": hook,
                "punchline": punchline,
                "surprise": surprise,
            }[name],
        )
        return Score(
            humor=humor,
            punchline=punchline,
            surprise=surprise,
            quotability=quotability,
            hook=hook,
            standalone=standalone,
            pacing=pacing,
            reaction=reaction,
            retention=retention,
            overall=overall,
            explanation=(
                f"Selected for strong {strongest}; scored locally from dialogue, timing, "
                "and punctuation."
            ),
        )


def choose_diverse(
    ranked: list[RankedCandidate], count: int, minimum: int = 1
) -> list[RankedCandidate]:
    chosen: list[RankedCandidate] = []
    remaining = list(ranked)
    while remaining and len(chosen) < count:
        best = max(
            remaining,
            key=lambda item: (
                item.score.overall
                - 0.75
                * max((_similarity(item.candidate, old.candidate) for old in chosen), default=0)
            ),
        )
        penalty = max((_similarity(best.candidate, old.candidate) for old in chosen), default=0)
        if penalty < 0.72 or len(chosen) < min(minimum, count):
            chosen.append(best)
        remaining.remove(best)
    return chosen


def automatic_clip_count(ranked: list[RankedCandidate], media_duration: float) -> int:
    """Choose a useful clip count from the episode and ranked moment pool."""
    if not ranked:
        return 0
    minimum = min(2, len(ranked))
    runtime_target = max(2, min(8, math.ceil(media_duration / 600) + 1))
    quality_floor = max(0.25, ranked[0].score.overall * 0.65)
    viable = sum(item.score.overall >= quality_floor for item in ranked)
    return min(len(ranked), runtime_target, max(minimum, viable))


def _similarity(first: Candidate, second: Candidate) -> float:
    overlap = max(0.0, min(first.end, second.end) - max(first.start, second.start))
    temporal = overlap / max(1.0, min(first.duration, second.duration))
    if overlap == 0 and abs(first.start - second.start) < 8:
        temporal = 0.65
    first_words = Counter(_content_words(first.transcript))
    second_words = Counter(_content_words(second.transcript))
    intersection = sum((first_words & second_words).values())
    union = sum((first_words | second_words).values())
    lexical = intersection / union if union else 0.0
    return max(temporal, lexical)


def _content_words(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z0-9']+", text.lower()) if word not in _STOP]


def _cap(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)
