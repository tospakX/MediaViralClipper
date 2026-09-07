"""Readable short caption cues and SRT/ASS serialization."""

from pydantic import Field

from clipper.models import FrozenModel, TranscriptSegment, Word
from clipper.timecode import format_srt_timestamp


class CaptionCue(FrozenModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str
    emphasis: tuple[str, ...] = ()
    tokens: tuple["CaptionToken", ...] = ()


class CaptionToken(FrozenModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str


def build_caption_cues(
    segments: list[TranscriptSegment],
    clip_start: float,
    clip_end: float,
    max_words: int = 4,
    max_characters: int = 20,
    playback_speed: float = 1.1,
    emphasize: bool = True,
) -> list[CaptionCue]:
    if max_words < 1:
        raise ValueError("max_words must be at least 1")
    if max_characters < 1:
        raise ValueError("max_characters must be at least 1")
    if playback_speed <= 0:
        raise ValueError("playback_speed must be positive")
    cues: list[CaptionCue] = []
    for segment in segments:
        if segment.end <= clip_start or segment.start >= clip_end:
            continue
        words = list(segment.words) or _estimated_words(segment)
        for chunk in _caption_chunks(words, max_words, max_characters):
            start = (max(clip_start, chunk[0].start) - clip_start) / playback_speed
            end = (min(clip_end, chunk[-1].end) - clip_start) / playback_speed
            text = " ".join(word.text.strip() for word in chunk).strip()
            emphasis = (
                tuple(
                    word.text.strip(".,!?")
                    for word in chunk
                    if word.text.endswith(("!", "?")) or len(word.text.strip(".,!?")) >= 10
                )
                if emphasize
                else ()
            )
            if text and end > start:
                tokens = tuple(
                    CaptionToken(
                        start=(max(clip_start, word.start) - clip_start) / playback_speed,
                        end=(min(clip_end, word.end) - clip_start) / playback_speed,
                        text=word.text.strip(),
                    )
                    for word in chunk
                    if word.text.strip() and min(clip_end, word.end) > max(clip_start, word.start)
                )
                cues.append(
                    CaptionCue(
                        start=start,
                        end=end,
                        text=text,
                        emphasis=emphasis,
                        tokens=tokens,
                    )
                )
    return cues


def _caption_chunks(words: list[Word], max_words: int, max_characters: int) -> list[list[Word]]:
    chunks: list[list[Word]] = []
    current: list[Word] = []
    current_length = 0
    for word in words:
        clean = word.text.strip()
        if not clean:
            continue
        next_length = current_length + (1 if current else 0) + len(clean)
        if current and (len(current) >= max_words or next_length > max_characters):
            chunks.append(current)
            current = []
            current_length = 0
        current.append(word)
        current_length += (1 if current_length else 0) + len(clean)
    if current:
        chunks.append(current)
    return chunks


def _estimated_words(segment: TranscriptSegment) -> list[Word]:
    tokens = segment.text.split()
    if not tokens:
        return []
    duration = segment.end - segment.start
    step = duration / len(tokens)
    return [
        Word(
            start=segment.start + index * step,
            end=segment.start + (index + 1) * step,
            text=token,
        )
        for index, token in enumerate(tokens)
    ]


def render_srt(cues: list[CaptionCue]) -> str:
    blocks = [
        f"{index}\n{format_srt_timestamp(cue.start)} --> "
        f"{format_srt_timestamp(cue.end)}\n{cue.text}"
        for index, cue in enumerate(cues, start=1)
    ]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def render_ass(
    cues: list[CaptionCue],
    width: int = 1080,
    height: int = 1920,
    style: str = "default",
) -> str:
    styles = {
        "default": (82, 6, 410),
        "bold": (90, 7, 410),
        "minimal": (64, 4, 360),
    }
    if style not in styles:
        raise ValueError(f"unknown caption style: {style}")
    font_size, outline, margin = styles[style]
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,"
        "BackColour,Bold,"
        "Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,"
        "Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Default,DejaVu Sans,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,"
        f"&H80000000,-1,0,0,0,100,100,0,0,1,{outline},1,2,96,96,{margin},1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    lines = [line for cue in cues for line in _ass_events(cue)]
    return header + "\n".join(lines) + ("\n" if lines else "")


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6000)
    whole, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole:02d}.{fraction:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def _ass_caption(cue: CaptionCue, active_index: int | None = None) -> str:
    emphasized = {word.casefold() for word in cue.emphasis}
    rendered: list[str] = []
    for index, token in enumerate(cue.text.split()):
        clean = token.strip(".,!?").casefold()
        escaped = _ass_escape(token)
        if index == active_index:
            rendered.append(r"{\fscx110\fscy110}{\b1\c&H0045FFFF&}" + escaped + r"{\r}")
        elif clean in emphasized:
            rendered.append(r"{\b1\c&H0045FFFF&}" + escaped + r"{\r}")
        else:
            rendered.append(escaped)
    return " ".join(rendered)


def _ass_events(cue: CaptionCue) -> list[str]:
    if not cue.tokens:
        return [_ass_event(cue.start, cue.end, _ass_caption(cue))]
    lines: list[str] = []
    for index, token in enumerate(cue.tokens):
        next_start = cue.tokens[index + 1].start if index + 1 < len(cue.tokens) else cue.end
        event_end = max(token.end, next_start)
        lines.append(_ass_event(token.start, event_end, _ass_caption(cue, index)))
    return lines


def _ass_event(start: float, end: float, text: str) -> str:
    return f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}"
