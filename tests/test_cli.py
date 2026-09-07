from pathlib import Path

from typer.testing import CliRunner

from clipper.cli import app

runner = CliRunner()


def test_help_lists_core_workflow_options() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "--clips" in result.stdout
    assert "--max-duration" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--vertical" in result.stdout
    assert "--captions" in result.stdout
    assert "--caption-style" in result.stdout


def test_missing_source_has_a_clear_nonzero_exit(tmp_path: Path) -> None:
    result = runner.invoke(app, [str(tmp_path / "missing episode.mkv"), "--dry-run"])

    assert result.exit_code != 0
    assert "does not exist" in result.output.lower()


def test_invalid_duration_window_is_rejected_before_analysis(tmp_path: Path) -> None:
    source = tmp_path / "episode.mkv"
    source.touch()

    result = runner.invoke(
        app,
        [str(source), "--min-duration", "30", "--max-duration", "20", "--dry-run"],
    )

    assert result.exit_code != 0
    assert "min_duration" in result.output
