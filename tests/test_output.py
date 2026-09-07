from pathlib import Path

from clipper.pipeline import episode_output_name


def test_output_name_is_safe_and_stable() -> None:
    assert episode_output_name(Path("Rick & Morty: S01 E01.mkv")) == "Rick_Morty_S01_E01"
    assert episode_output_name(Path("..mkv")) == "episode"
