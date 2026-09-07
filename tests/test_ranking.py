from clipper.models import Candidate, RankedCandidate, Score
from clipper.ranking import HeuristicRanker, automatic_clip_count, choose_diverse


def _candidate(identifier: str, start: float, text: str) -> Candidate:
    return Candidate(
        id=identifier,
        start=start,
        end=start + 20,
        transcript=text,
        segment_indices=(0, 1),
    )


def _ranked(candidate: Candidate, overall: float) -> RankedCandidate:
    score = Score(
        humor=overall,
        punchline=overall,
        surprise=overall,
        quotability=overall,
        hook=overall,
        standalone=overall,
        pacing=overall,
        reaction=overall,
        retention=overall,
        overall=overall,
        explanation="fixture",
    )
    return RankedCandidate(candidate=candidate, score=score)


def test_heuristic_rewards_hook_punchline_and_surprise() -> None:
    funny = _candidate("funny", 0, "Wait, what?! A talking horse? That's impossible—ha ha!")
    flat = _candidate("flat", 50, "They continued walking through the room and then sat down.")

    ranked = HeuristicRanker().rank([flat, funny])

    assert ranked[0].candidate.id == "funny"
    assert ranked[0].score.hook > ranked[1].score.hook
    assert ranked[0].score.punchline > ranked[1].score.punchline


def test_diversity_suppresses_overlaps_and_repeated_jokes() -> None:
    best = _ranked(_candidate("a", 0, "The horse wants dessert."), 0.95)
    overlap = _ranked(_candidate("b", 5, "The horse wants dessert too."), 0.93)
    different = _ranked(_candidate("c", 120, "The robot accidentally became mayor."), 0.80)

    chosen = choose_diverse([best, overlap, different], count=2)

    assert [item.candidate.id for item in chosen] == ["a", "c"]


def test_diversity_keeps_only_one_moment_from_a_nearby_story_sequence() -> None:
    first = _ranked(_candidate("first", 0, "The teacher starts a surprise exam."), 0.95)
    same_sequence = _ranked(
        _candidate("same-sequence", 55, "A student argues with someone in the hallway."), 0.92
    )
    different = _ranked(_candidate("different", 180, "The robot becomes mayor."), 0.80)

    chosen = choose_diverse([first, same_sequence, different], count=2)

    assert [item.candidate.id for item in chosen] == ["first", "different"]


def test_automatic_clip_count_uses_runtime_and_viable_distinct_moments() -> None:
    ranked = [
        _ranked(_candidate(f"clip-{index}", index * 60, f"Distinct moment number {index}."), score)
        for index, score in enumerate((0.91, 0.82, 0.74, 0.63, 0.31, 0.18))
    ]

    assert automatic_clip_count(ranked, media_duration=20 * 60) == 3
    assert automatic_clip_count(ranked, media_duration=50 * 60) == 3


def test_automatic_clip_count_can_return_one_when_only_one_moment_is_viable() -> None:
    ranked = [
        _ranked(_candidate("best", 0, "First complete moment."), 0.42),
        _ranked(_candidate("second", 80, "Second complete moment."), 0.20),
    ]

    assert automatic_clip_count(ranked, media_duration=8 * 60) == 1


def test_automatic_diversity_keeps_two_when_every_candidate_is_similar() -> None:
    best = _ranked(_candidate("best", 0, "The same complete joke lands here."), 0.90)
    overlap = _ranked(_candidate("overlap", 2, "The same complete joke lands here."), 0.75)

    chosen = choose_diverse([best, overlap], count=8, minimum=2)

    assert [item.candidate.id for item in chosen] == ["best", "overlap"]
