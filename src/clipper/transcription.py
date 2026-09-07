"""Embedded subtitle extraction and local faster-whisper transcription."""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from clipper.config import ClipperConfig
from clipper.models import MediaInfo, SubtitleTrack, TranscriptSegment, Word
from clipper.process import CommandError, run_command
from clipper.timecode import parse_timestamp

_TIMING_LINE = re.compile(
    r"(?P<start>\d\d:\d\d:\d\d[,.]\d+)\s+-->\s+(?P<end>\d\d:\d\d:\d\d[,.]\d+)"
)
_TAGS = re.compile(r"<[^>]+>|\{\\[^}]+\}")
_WEB_ADDRESS = re.compile(
    r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)+(?:/\S*)?[.,!?;:]*", re.IGNORECASE
)


def parse_srt(content: str) -> list[TranscriptSegment]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    result: list[TranscriptSegment] = []
    for block in re.split(r"\n\s*\n", normalized):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = _TIMING_LINE.search(lines[timing_index])
        if not match:
            continue
        text = _clean_subtitle_text(
            " ".join(_TAGS.sub("", line).strip() for line in lines[timing_index + 1 :])
        )
        if not text:
            continue
        start = parse_timestamp(match.group("start"))
        end = parse_timestamp(match.group("end"))
        if result and start < result[-1].end:
            prior = result[-1].model_copy(update={"end": max(result[-1].start + 0.001, start)})
            result[-1] = prior
        if end > start:
            result.append(TranscriptSegment(start=start, end=end, text=text))
    return result


def _clean_subtitle_text(text: str) -> str:
    without_addresses = _WEB_ADDRESS.sub("", text)
    return re.sub(r"\s+", " ", without_addresses).strip(" \t,;:-")


def extract_embedded_subtitles(
    source: Path,
    media: MediaInfo,
    runner: Callable[[list[str]], str] = run_command,
    language: str | None = None,
) -> list[TranscriptSegment]:
    tracks = media.subtitle_tracks or tuple(
        SubtitleTrack(index=index) for index in media.subtitle_streams
    )
    viable: list[tuple[float, list[TranscriptSegment]]] = []
    for track in tracks:
        arguments = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(source),
            "-map",
            f"0:{track.index}",
            "-f",
            "srt",
            "-",
        ]
        try:
            segments = parse_srt(runner(arguments))
        except CommandError:
            continue
        spoken_chars = sum(len(segment.text) for segment in segments)
        coverage = sum(segment.end - segment.start for segment in segments)
        if spoken_chars < max(40, media.duration * 0.25):
            continue
        if coverage < max(4.0, media.duration * 0.02):
            continue
        score = min(1.0, coverage / max(1.0, media.duration * 0.08))
        score += min(1.0, spoken_chars / max(1.0, media.duration * 2.0))
        if track.default:
            score += 0.3
        if language and _languages_match(language, track.language):
            score += 2.0
        title = (track.title or "").lower()
        if track.forced or any(word in title for word in ("forced", "sign", "song")):
            score -= 3.0
        if any(word in title for word in ("commentary", "director")):
            score -= 2.0
        viable.append((score, segments))
    return max(viable, key=lambda item: item[0])[1] if viable else []


def transcribe_media(
    source: Path,
    media: MediaInfo,
    config: ClipperConfig,
    runner: Callable[[list[str]], str] = run_command,
    model_factory: Callable[..., Any] | None = None,
) -> list[TranscriptSegment]:
    if config.use_embedded_subtitles and media.subtitle_streams:
        embedded = extract_embedded_subtitles(source, media, runner, config.language)
        if embedded:
            return merge_dialogue_segments(embedded)
    if model_factory is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise RuntimeError(
                "No usable embedded subtitles. Install analysis dependencies with "
                "`uv sync --extra analysis` to enable faster-whisper."
            ) from error
        model_factory = WhisperModel
    requested_device = config.device
    device = requested_device
    if device == "auto":
        device = "cuda" if _nvidia_available() else "cpu"
    try:
        raw_segments = _run_whisper(model_factory, source, config, device, config.compute_type)
    except (RuntimeError, OSError):
        if requested_device != "auto" or device != "cuda":
            raise
        cpu_compute_type = (
            "int8"
            if config.compute_type in {"auto", "float16", "int8_float16"}
            else config.compute_type
        )
        raw_segments = _run_whisper(model_factory, source, config, "cpu", cpu_compute_type)
    return merge_dialogue_segments(_convert_whisper_segments(raw_segments))


def merge_dialogue_segments(
    segments: list[TranscriptSegment], max_gap: float = 1.5, max_duration: float = 12.0
) -> list[TranscriptSegment]:
    """Join tokenizer-sized fragments without creating overly long dialogue blocks."""
    merged: list[TranscriptSegment] = []
    pending: TranscriptSegment | None = None
    for segment in segments:
        if pending is None:
            pending = segment
        elif (
            not _sentence_complete(pending.text)
            and segment.start - pending.end <= max_gap
            and segment.end - pending.start <= max_duration
        ):
            pending = pending.model_copy(
                update={
                    "end": segment.end,
                    "text": f"{pending.text.rstrip()} {segment.text.lstrip()}",
                    "words": pending.words + segment.words,
                }
            )
        else:
            merged.append(pending)
            pending = segment
        if pending is not None and _sentence_complete(pending.text):
            merged.append(pending)
            pending = None
    if pending is not None:
        merged.append(pending)
    return merged


def _sentence_complete(text: str) -> bool:
    return text.rstrip().endswith((".", "?", "!", "…", ".”", "!”", "?”", '!"'))


def _languages_match(requested: str, available: str | None) -> bool:
    if not available:
        return False
    aliases = {
        "en": "eng",
        "eng": "eng",
        "tr": "tur",
        "tur": "tur",
        "de": "deu",
        "deu": "deu",
        "ger": "deu",
        "fr": "fra",
        "fra": "fra",
        "fre": "fra",
        "es": "spa",
        "spa": "spa",
    }
    return aliases.get(requested.lower(), requested.lower()) == aliases.get(
        available.lower(), available.lower()
    )


def _run_whisper(
    model_factory: Callable[..., Any],
    source: Path,
    config: ClipperConfig,
    device: str,
    compute_type: str,
) -> list[Any]:
    """Run and eagerly consume Whisper so lazy CUDA failures are recoverable."""
    model = model_factory(config.whisper_model, device=device, compute_type=compute_type)
    raw_segments, _info = model.transcribe(
        str(source),
        language=config.language,
        vad_filter=True,
        word_timestamps=True,
        beam_size=5,
    )
    return list(raw_segments)


def _convert_whisper_segments(raw_segments: list[Any]) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    for segment in raw_segments:
        words = tuple(
            Word(
                start=max(0.0, float(word.start)),
                end=float(word.end),
                text=str(word.word).strip(),
                probability=float(word.probability),
            )
            for word in (segment.words or ())
            if word.start is not None and word.end is not None and str(word.word).strip()
        )
        text = str(segment.text).strip()
        if text and float(segment.end) > float(segment.start):
            segments.append(
                TranscriptSegment(
                    start=max(0.0, float(segment.start)),
                    end=float(segment.end),
                    text=text,
                    words=words,
                )
            )
    return segments


def _nvidia_available() -> bool:
    from shutil import which

    return which("nvidia-smi") is not None
