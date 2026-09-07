"""Time parsing and subtitle serialization."""

import re

_TIMESTAMP = re.compile(r"^(?:(?P<h>\d+):)?(?P<m>\d{1,2}):(?P<s>\d{1,2}(?:[.,]\d+)?)$")


def parse_timestamp(value: str) -> float:
    match = _TIMESTAMP.fullmatch(value.strip())
    if not match:
        raise ValueError(f"invalid timestamp: {value!r}")
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m"))
    seconds = float(match.group("s").replace(",", "."))
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"invalid timestamp: {value!r}")
    return hours * 3600 + minutes * 60 + seconds


def format_srt_timestamp(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{millis:03d}"


def format_ffmpeg_timestamp(seconds: float) -> str:
    return f"{max(0.0, seconds):.3f}"
