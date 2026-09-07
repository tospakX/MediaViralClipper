"""Validated runtime configuration."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClipperConfig(BaseModel):
    """All pipeline controls, suitable for stable JSON fingerprinting."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    clips: Annotated[int, Field(ge=1, le=20)] | Literal["auto"] = 3
    min_duration: float = Field(default=15.0, gt=0)
    max_duration: float = Field(default=40.0, gt=0, le=300)
    target_duration: float = Field(default=28.0, gt=0)
    vertical: bool = True
    captions: bool = True
    output: Path = Path("output")
    whisper_model: str = "small"
    language: str | None = None
    device: Literal["auto", "cpu", "cuda"] = "auto"
    compute_type: str = "auto"
    workers: int = Field(default=2, ge=1, le=16)
    scene_threshold: float = Field(default=27.0, gt=0, le=100)
    use_embedded_subtitles: bool = True
    ranker: Literal["heuristic", "ollama", "openai-compatible"] = "heuristic"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:1.7b"
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key_env: str = "CLIPPER_LLM_API_KEY"
    hardware_encoding: Literal["auto", "cpu", "nvenc"] = "auto"
    emphasize_words: bool = True
    caption_style: Literal["default", "bold", "minimal"] = "bold"
    playback_speed: float = Field(default=1.1, ge=0.5, le=2.0)
    overwrite: bool = False

    @model_validator(mode="after")
    def validate_durations(self) -> "ClipperConfig":
        if self.min_duration > self.max_duration:
            raise ValueError("min_duration must not exceed max_duration")
        if not self.min_duration <= self.target_duration <= self.max_duration:
            raise ValueError("target_duration must be within min_duration and max_duration")
        if self.ranker == "openai-compatible" and not (self.llm_base_url and self.llm_model):
            raise ValueError(
                "llm_base_url and llm_model are required for openai-compatible ranking"
            )
        return self
