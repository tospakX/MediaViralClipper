import pytest
from pydantic import ValidationError

from clipper.config import ClipperConfig


def test_default_duration_window_is_short_form_safe() -> None:
    config = ClipperConfig()

    assert config.min_duration == 15.0
    assert config.max_duration == 40.0
    assert config.target_duration == 28.0
    assert config.playback_speed == 1.1
    assert config.caption_style == "bold"


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"min_duration": 0}, "min_duration"),
        ({"min_duration": 30, "max_duration": 20}, "min_duration"),
        ({"clips": 0}, "clips"),
        ({"target_duration": 41}, "target_duration"),
        ({"playback_speed": 0.49}, "playback_speed"),
    ],
)
def test_invalid_configuration_is_rejected(values: dict[str, float], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        ClipperConfig(**values)


def test_explicit_hard_maximum_can_exceed_default() -> None:
    config = ClipperConfig(max_duration=55, target_duration=45)

    assert config.max_duration == 55


def test_unknown_caption_style_is_rejected() -> None:
    with pytest.raises(ValidationError, match="caption_style"):
        ClipperConfig(caption_style="giant-random-style")
