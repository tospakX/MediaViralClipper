"""Command-line interface."""

from pathlib import Path
from typing import Annotated, Literal

import typer
from pydantic import ValidationError
from rich.console import Console

from clipper.config import ClipperConfig
from clipper.pipeline import ClipperPipeline
from clipper.state import Stage, StageStatus

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Find, rank, and export coherent funny/engaging clips from a local video.",
)
console = Console()


def _progress(stage: Stage, status: StageStatus, message: str) -> None:
    icon = {
        StageStatus.STARTED: "…",
        StageStatus.CACHED: "↺",
        StageStatus.COMPLETED: "✓",
        StageStatus.FAILED: "✗",
    }[status]
    console.print(f"[dim]{icon}[/dim] [bold]{stage.value}[/bold]: {message}")


@app.command()
def main(
    source: Annotated[
        Path,
        typer.Argument(
            exists=True, file_okay=True, dir_okay=False, readable=True, resolve_path=True
        ),
    ],
    clips: Annotated[int, typer.Option("--clips", min=1, max=20)] = 3,
    min_duration: Annotated[float, typer.Option("--min-duration", min=0.1)] = 15.0,
    max_duration: Annotated[float, typer.Option("--max-duration", min=0.1)] = 40.0,
    vertical: Annotated[bool, typer.Option("--vertical/--no-vertical")] = True,
    captions: Annotated[bool, typer.Option("--captions/--no-captions")] = True,
    caption_style: Annotated[
        Literal["default", "bold", "minimal"], typer.Option("--caption-style")
    ] = "bold",
    playback_speed: Annotated[float, typer.Option("--playback-speed", min=0.5, max=2.0)] = 1.1,
    output: Annotated[Path, typer.Option("--output", file_okay=False)] = Path("output"),
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    whisper_model: Annotated[str, typer.Option("--whisper-model")] = "small",
    language: Annotated[str | None, typer.Option("--language")] = None,
    device: Annotated[
        Literal["auto", "cpu", "cuda"], typer.Option("--device", help="auto, cpu, or cuda")
    ] = "auto",
    compute_type: Annotated[str, typer.Option("--compute-type")] = "auto",
    workers: Annotated[int, typer.Option("--workers", min=1, max=16)] = 2,
    scene_threshold: Annotated[float, typer.Option("--scene-threshold", min=0.1, max=100)] = 27.0,
    hardware_encoding: Annotated[
        Literal["auto", "cpu", "nvenc"],
        typer.Option("--hardware-encoding", help="auto, cpu, or nvenc"),
    ] = "auto",
    ranker: Annotated[
        Literal["heuristic", "ollama", "openai-compatible"],
        typer.Option("--ranker", help="ollama, heuristic, or openai-compatible"),
    ] = "ollama",
    ollama_base_url: Annotated[str, typer.Option("--ollama-base-url")] = ("http://127.0.0.1:11434"),
    ollama_model: Annotated[str, typer.Option("--ollama-model")] = "qwen3:1.7b",
    llm_base_url: Annotated[str | None, typer.Option("--llm-base-url")] = None,
    llm_model: Annotated[str | None, typer.Option("--llm-model")] = None,
) -> None:
    try:
        config = ClipperConfig(
            clips=clips,
            min_duration=min_duration,
            max_duration=max_duration,
            target_duration=min(max(28.0, min_duration), max_duration),
            vertical=vertical,
            captions=captions,
            caption_style=caption_style,
            playback_speed=playback_speed,
            output=output,
            whisper_model=whisper_model,
            language=language,
            device=device,
            compute_type=compute_type,
            workers=workers,
            scene_threshold=scene_threshold,
            hardware_encoding=hardware_encoding,
            ranker=ranker,
            ollama_base_url=ollama_base_url,
            ollama_model=ollama_model,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
        )
    except ValidationError as error:
        raise typer.BadParameter(str(error)) from error
    try:
        result = ClipperPipeline(config, progress=_progress).run(source, dry_run=dry_run)
    except Exception as error:
        console.print(f"[red]Error:[/red] {error}")
        raise typer.Exit(code=1) from error
    console.print(f"\n[green]Output:[/green] {result.episode_directory}")
    console.print(f"Selected {len(result.selections)} clip(s){' (dry run)' if dry_run else ''}.")
    failures = [render for render in result.renders if render.error]
    if failures:
        console.print(
            f"[yellow]{len(failures)} clip render(s) failed; "
            "inspect metadata.json/run.jsonl.[/yellow]"
        )
