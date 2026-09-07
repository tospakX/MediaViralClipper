from clipper.timecode import format_srt_timestamp, parse_timestamp


def test_srt_timestamp_rounds_carry_into_next_second() -> None:
    assert format_srt_timestamp(59.9996) == "00:01:00,000"


def test_parse_timestamp_accepts_srt_and_ffmpeg_forms() -> None:
    assert parse_timestamp("01:02:03,500") == 3723.5
    assert parse_timestamp("02:03.250") == 123.25


def test_negative_timestamp_is_clamped_for_serialization() -> None:
    assert format_srt_timestamp(-0.5) == "00:00:00,000"
