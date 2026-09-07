from pathlib import Path
from types import SimpleNamespace

import pytest

from clipper.config import ClipperConfig
from clipper.models import MediaInfo, SubtitleTrack, TranscriptSegment
from clipper.transcription import (
    extract_embedded_subtitles,
    merge_dialogue_segments,
    parse_srt,
    transcribe_media,
)


def test_srt_parser_keeps_multiline_text_and_punctuation() -> None:
    content = """1
00:00:01,000 --> 00:00:03,200
Wait—what?
No way!

2
00:00:04,000 --> 00:00:05,000
Exactly.
"""

    segments = parse_srt(content)

    assert segments[0].text == "Wait—what? No way!"
    assert (segments[0].start, segments[0].end) == (1.0, 3.2)
    assert segments[1].text == "Exactly."


def test_srt_parser_repairs_overlap_without_clipping_words() -> None:
    content = """1
00:00:01,000 --> 00:00:03,000
First sentence.

2
00:00:02,800 --> 00:00:04,000
Second sentence.
"""

    segments = parse_srt(content)

    assert segments[0].end == 2.8
    assert segments[1].start == 2.8


def test_embedded_subtitles_reject_short_forced_sign_track() -> None:
    media = MediaInfo(
        source=Path("episode.mkv"),
        duration=1200,
        width=1920,
        height=1080,
        fps=24,
        video_codec="h264",
        subtitle_streams=(2, 3),
        subtitle_tracks=(
            SubtitleTrack(index=2, codec="subrip", language="eng", title="Signs", forced=True),
            SubtitleTrack(index=3, codec="subrip", language="eng", title="English", default=True),
        ),
    )
    signs = """1\n00:01:00,000 --> 00:01:06,000\nTHE HOTEL\n"""
    dialogue = "\n\n".join(
        f"{index}\n00:{minute:02d}:00,000 --> 00:{minute:02d}:08,000\n"
        f"This is complete spoken dialogue number {index}."
        for index, minute in enumerate(range(1, 11), start=1)
    )

    def runner(arguments: list[str]) -> str:
        return signs if "0:2" in arguments else dialogue

    segments = extract_embedded_subtitles(Path("episode.mkv"), media, runner)

    assert len(segments) == 10
    assert segments[0].text.startswith("This is complete")


def test_embedded_subtitles_prefer_requested_language() -> None:
    media = MediaInfo(
        source=Path("episode.mkv"),
        duration=120,
        width=1920,
        height=1080,
        fps=24,
        video_codec="h264",
        subtitle_streams=(2, 3),
        subtitle_tracks=(
            SubtitleTrack(index=2, codec="subrip", language="eng", default=True),
            SubtitleTrack(index=3, codec="subrip", language="tur"),
        ),
    )
    english = (
        "1\n00:00:10,000 --> 00:00:20,000\nThis is long enough English dialogue for selection.\n"
    )
    turkish = (
        "1\n00:00:10,000 --> 00:00:20,000\nBu secim icin yeterince uzun Turkce bir diyalogdur.\n"
    )

    def runner(arguments: list[str]) -> str:
        return english if "0:2" in arguments else turkish

    segments = extract_embedded_subtitles(Path("episode.mkv"), media, runner, language="tr")

    assert segments[0].text.startswith("Bu secim")


def test_fragmented_dialogue_is_merged_into_complete_sentences() -> None:
    segments = [
        TranscriptSegment(start=4, end=5, text="you replaced the mayor"),
        TranscriptSegment(start=5.2, end=6, text="with a cardboard robot?"),
        TranscriptSegment(start=7, end=8, text="Yes."),
    ]

    merged = merge_dialogue_segments(segments)

    assert [(item.start, item.end, item.text) for item in merged] == [
        (4, 6, "you replaced the mayor with a cardboard robot?"),
        (7, 8, "Yes."),
    ]


def test_auto_cuda_failure_retries_whisper_on_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class CpuModel:
        def transcribe(self, source: str, **options: object) -> tuple[list[object], object]:
            segment = SimpleNamespace(start=1, end=3, text="Recovered dialogue.", words=[])
            return [segment], object()

    def factory(model: str, *, device: str, compute_type: str) -> object:
        calls.append((device, compute_type))
        if device == "cuda":
            raise RuntimeError("CUDA libraries unavailable")
        return CpuModel()

    monkeypatch.setattr("clipper.transcription._nvidia_available", lambda: True)
    media = MediaInfo(
        source=Path("episode.mkv"),
        duration=60,
        width=320,
        height=180,
        fps=24,
        video_codec="h264",
    )

    segments = transcribe_media(Path("episode.mkv"), media, ClipperConfig(), model_factory=factory)

    assert calls == [("cuda", "auto"), ("cpu", "int8")]
    assert segments[0].text == "Recovered dialogue."


def test_explicit_cuda_failure_is_not_silently_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def factory(model: str, *, device: str, compute_type: str) -> object:
        calls.append(device)
        raise RuntimeError("CUDA libraries unavailable")

    media = MediaInfo(
        source=Path("episode.mkv"),
        duration=60,
        width=320,
        height=180,
        fps=24,
        video_codec="h264",
    )

    with pytest.raises(RuntimeError, match="CUDA"):
        transcribe_media(
            Path("episode.mkv"),
            media,
            ClipperConfig(device="cuda"),
            model_factory=factory,
        )

    assert calls == ["cuda"]
