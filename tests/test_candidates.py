from clipper.candidates import generate_candidates
from clipper.config import ClipperConfig
from clipper.models import AudioInterval, Scene, TranscriptSegment


def _dialogue() -> list[TranscriptSegment]:
    return [
        TranscriptSegment(start=1, end=5, text="You brought a horse into the kitchen?"),
        TranscriptSegment(start=5.4, end=9, text="He said he knew the chef."),
        TranscriptSegment(start=10, end=14, text="The horse said that?"),
        TranscriptSegment(start=14.5, end=18, text="No, the chef did."),
        TranscriptSegment(start=19, end=23, text="That somehow raises more questions."),
        TranscriptSegment(start=24, end=29, text="Anyway, the horse wants dessert."),
        TranscriptSegment(start=31, end=36, text="Of course he does!"),
    ]


def test_candidates_obey_duration_and_sentence_boundaries() -> None:
    config = ClipperConfig(min_duration=15, max_duration=30, target_duration=22)

    candidates = generate_candidates(
        _dialogue(), [Scene(start=0, end=40)], config, media_duration=40
    )

    assert candidates
    assert all(15 <= item.duration <= 30 for item in candidates)
    assert all(item.transcript[-1] in ".?!" for item in candidates)
    assert all(item.start in {segment.start for segment in _dialogue()} for item in candidates)


def test_candidate_ids_and_order_are_deterministic() -> None:
    config = ClipperConfig(min_duration=15, max_duration=30, target_duration=22)

    first = generate_candidates(_dialogue(), [Scene(start=0, end=40)], config, 40)
    second = generate_candidates(_dialogue(), [Scene(start=0, end=40)], config, 40)

    assert [item.id for item in first] == [item.id for item in second]


def test_candidates_include_scene_change_and_audio_reaction_signals() -> None:
    config = ClipperConfig(min_duration=15, max_duration=30, target_duration=22)
    scenes = [Scene(start=0, end=12), Scene(start=12, end=25), Scene(start=25, end=40)]
    audio = [
        AudioInterval(start=0, end=20, rms=0.1, peak=0.2),
        AudioInterval(start=20, end=40, rms=0.5, peak=0.9),
    ]

    candidates = generate_candidates(_dialogue(), scenes, config, 40, audio=audio)

    spanning = next(item for item in candidates if item.start == 1 and item.end == 23)
    assert spanning.features["scene_changes"] == 1
    assert spanning.features["audio_peak"] == 0.9
    assert spanning.features["audio_rms"] == 0.3


def test_candidates_do_not_start_on_lowercase_sentence_fragments() -> None:
    dialogue = [
        TranscriptSegment(start=4, end=7, text="you replaced the mayor with a robot."),
        TranscriptSegment(start=7.2, end=11, text="That explains the campaign posters."),
        TranscriptSegment(start=11.5, end=16, text="Nobody noticed for three weeks!"),
        TranscriptSegment(start=16.5, end=22, text="Honestly, his approval rating went up."),
    ]
    config = ClipperConfig(min_duration=8, max_duration=18, target_duration=12)

    candidates = generate_candidates(dialogue, [Scene(start=0, end=25)], config, 25)

    assert candidates
    assert all(not item.transcript[0].islower() for item in candidates)
