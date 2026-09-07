from clipper.config import ClipperConfig
from clipper.models import Candidate, TranscriptSegment
from clipper.refine import refine_candidate


def test_refinement_adds_context_and_finishes_after_reaction() -> None:
    segments = [
        TranscriptSegment(start=8, end=10, text="So here's the plan."),
        TranscriptSegment(start=10.5, end=20, text="We replace the mayor with a pigeon."),
        TranscriptSegment(start=20.4, end=23, text="That is your plan?!"),
        TranscriptSegment(start=23.5, end=25, text="It polls well."),
    ]
    candidate = Candidate(id="x", start=10.5, end=23, transcript="middle", segment_indices=(1, 2))
    config = ClipperConfig(min_duration=15, max_duration=20, target_duration=18)

    refined = refine_candidate(candidate, segments, config, media_duration=30)

    assert refined.start == 8
    assert refined.end == 25
    assert refined.duration <= 20
    assert refined.transcript.endswith("It polls well.")


def test_refinement_never_exceeds_configured_hard_cap() -> None:
    segments = [
        TranscriptSegment(start=index * 6, end=index * 6 + 5, text=f"Sentence {index}.")
        for index in range(10)
    ]
    candidate = Candidate(
        id="x", start=6, end=35, transcript="middle", segment_indices=(1, 2, 3, 4, 5)
    )
    config = ClipperConfig(min_duration=15, max_duration=40, target_duration=28)

    refined = refine_candidate(candidate, segments, config, media_duration=60)

    assert refined.duration <= 40
    assert refined.start in {segment.start for segment in segments}
    assert refined.end in {segment.end for segment in segments}
