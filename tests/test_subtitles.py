import pytest

from clipper.models import TranscriptSegment, Word
from clipper.subtitles import build_caption_cues, render_ass, render_srt


def test_captions_are_short_and_preserve_punctuation() -> None:
    segment = TranscriptSegment(
        start=10,
        end=14,
        text="This ridiculous machine actually works, somehow!",
        words=tuple(
            Word(start=10 + index * 0.5, end=10.4 + index * 0.5, text=word)
            for index, word in enumerate(
                ["This", "ridiculous", "machine", "actually", "works,", "somehow!"]
            )
        ),
    )

    cues = build_caption_cues(
        [segment], clip_start=10, clip_end=14, max_words=3, max_characters=100
    )

    assert [cue.text for cue in cues] == ["This ridiculous machine", "actually works, somehow!"]
    assert cues[0].start == 0
    assert render_srt(cues).endswith("actually works, somehow!\n")


def test_ass_emphasizes_detected_punchline_words_without_changing_srt() -> None:
    segment = TranscriptSegment(start=0, end=2, text="That is absolutely ridiculous!")
    cues = build_caption_cues([segment], clip_start=0, clip_end=2, emphasize=True)

    ass = render_ass(cues, style="bold")

    assert r"{\b1\c&H0045FFFF&}absolutely{\r}" in ass
    assert "absolutely" in render_srt(cues)


def test_default_captions_fit_short_portrait_lines() -> None:
    words = [
        "Günaydın",  # noqa: RUF001 - intentional Turkish subtitle text
        "Frank.",
        "Günaydın",  # noqa: RUF001 - intentional Turkish subtitle text
        "mı?",  # noqa: RUF001 - intentional Turkish subtitle text
        "Ne",
        "demek",
        "istiyorsun?",
    ]
    segment = TranscriptSegment(
        start=10,
        end=17,
        text=" ".join(words),
        words=tuple(
            Word(start=10 + index, end=10.8 + index, text=word) for index, word in enumerate(words)
        ),
    )

    cues = build_caption_cues([segment], clip_start=10, clip_end=17, playback_speed=1)

    assert [word for cue in cues for word in cue.text.split()] == words
    assert all(len(cue.text.split()) <= 4 for cue in cues)
    assert all(len(cue.text) <= 20 for cue in cues)


def test_caption_and_token_times_follow_playback_speed() -> None:
    segment = TranscriptSegment(
        start=10,
        end=12.2,
        text="Well that escalated quickly!",
        words=(
            Word(start=10, end=10.5, text="Well"),
            Word(start=10.5, end=11, text="that"),
            Word(start=11, end=11.6, text="escalated"),
            Word(start=11.6, end=12.2, text="quickly!"),
        ),
    )

    cue = build_caption_cues(
        [segment],
        clip_start=10,
        clip_end=12.2,
        max_characters=100,
        playback_speed=1.1,
    )[0]

    assert cue.start == 0
    assert cue.end == pytest.approx(2.2 / 1.1)
    assert cue.tokens[2].start == pytest.approx(1 / 1.1)
    assert cue.tokens[2].end == pytest.approx(1.6 / 1.1)


def test_ass_uses_mobile_safe_wrapping_and_active_word_events() -> None:
    segment = TranscriptSegment(
        start=0,
        end=2,
        text="That is ridiculous!",
        words=(
            Word(start=0, end=0.5, text="That"),
            Word(start=0.5, end=1, text="is"),
            Word(start=1, end=2, text="ridiculous!"),
        ),
    )
    cue = build_caption_cues([segment], clip_start=0, clip_end=2, playback_speed=1)[0]

    ass = render_ass([cue], style="bold")

    assert "WrapStyle: 0" in ass
    assert ",96,96,410,1" in ass
    assert ass.count("Dialogue: 0,") == len(cue.tokens)
    assert r"\c&H0045FFFF&" in ass
    assert r"\fscx" not in ass
    assert r"\fscy" not in ass


def test_caption_chunks_never_mix_dash_prefixed_speaker_turns() -> None:
    words = ("Neden", "bildirmediniz?", "-Size", "bildirdim", "zaten.")
    segment = TranscriptSegment(
        start=0,
        end=5,
        text="Neden bildirmediniz? -Size bildirdim zaten.",
        words=tuple(
            Word(start=index, end=index + 0.8, text=word) for index, word in enumerate(words)
        ),
    )

    cues = build_caption_cues(
        [segment],
        clip_start=0,
        clip_end=5,
        max_words=6,
        max_characters=100,
        playback_speed=1,
    )

    assert [cue.text for cue in cues] == ["Neden bildirmediniz?", "-Size bildirdim zaten."]
