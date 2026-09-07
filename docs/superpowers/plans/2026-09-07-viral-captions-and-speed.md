# Viral Portrait Captions and Speed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce mobile-safe, high-retention portrait captions and synchronize every final clip at 1.10× playback speed.

**Architecture:** Keep caption segmentation in `subtitles.py`, but retain relative word timings so ASS can render an active-word highlight. Apply identical video/audio speed filters in `render.py`, scale SRT/ASS timestamps in the caption builder, and pass a validated speed through configuration and pipeline rendering.

**Tech Stack:** Python 3.12, Pydantic, FFmpeg/libass, pytest, ffprobe, Ollama ranking.

**Spec:** User request in the current conversation plus observed S1E1 portrait-caption failure.

## Global Constraints

- Preserve finished source media and existing MP4/SRT outputs until replacements render successfully.
- Final vertical canvas remains exactly 1080×1920, SAR 1:1, DAR 9:16.
- Captions must stay inside portrait horizontal and bottom-platform safe zones.
- Audio pitch must remain natural at 1.10×.
- Exported SRT timing must match the accelerated video.
- Rendering failures remain isolated per clip.

---

### Task 1: Width-Aware Portrait Caption Cues

**Files:**
- Modify: `src/clipper/subtitles.py`
- Test: `tests/test_subtitles.py`

**Interfaces:**
- Consumes: `TranscriptSegment` and word-level timestamps.
- Produces: `build_caption_cues(..., max_words=4, max_characters=20, playback_speed=1.1) -> list[CaptionCue]`.

- [x] Add tests showing a long Turkish sentence becomes short cues of at most four words and 20 characters where word boundaries permit.
- [x] Add a test showing cue and token timestamps divide by 1.10.
- [x] Run `uv run pytest -q tests/test_subtitles.py` and confirm the new assertions fail for the missing behavior.
- [x] Add relative timed tokens to `CaptionCue` and implement word/character-aware chunking.
- [x] Run `uv run pytest -q tests/test_subtitles.py` and confirm it passes.

### Task 2: Mobile-Safe Active-Word ASS

**Files:**
- Modify: `src/clipper/subtitles.py`
- Test: `tests/test_subtitles.py`

**Interfaces:**
- Consumes: timed `CaptionCue` tokens from Task 1.
- Produces: ASS at 1080×1920 with smart wrapping, 96-pixel side margins, a lower-middle safe baseline, and per-token highlight events.

- [x] Add a test requiring `WrapStyle: 0`, explicit portrait margins, and one active-word event per timed token.
- [x] Confirm the test fails against the current no-wrap single-event renderer.
- [x] Implement bold white text, black outline, yellow active token, and safe vertical placement.
- [x] Confirm subtitle tests pass and render a synthetic frame whose non-background caption pixels stay inside the safe bounds.

### Task 3: Synchronized 1.10× Final Rendering

**Files:**
- Modify: `src/clipper/config.py`
- Modify: `src/clipper/web_jobs.py`
- Modify: `src/clipper/cli.py`
- Modify: `src/clipper/render.py`
- Modify: `src/clipper/pipeline.py`
- Test: `tests/test_config.py`
- Test: `tests/test_render.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `ClipperConfig.playback_speed: float = 1.10`.
- Produces: FFmpeg filters `setpts=PTS/1.1000` and `atempo=1.1000`, plus speed-adjusted SRT/ASS timestamps.

- [x] Add failing tests for the default speed, speed validation, video PTS filter, audio tempo filter, and input-side trim ordering.
- [x] Add `playback_speed` to config, web options, CLI, pipeline captioning, render fingerprints, and metadata.
- [x] Pass the speed to original and vertical command builders and apply equal video/audio acceleration.
- [x] Run focused render, config, pipeline, and subtitle tests.

### Task 4: Real Output Verification

**Files:**
- Verify: `~/Downloads/MediaViralClipper/S1E1/clip_*/vertical.mp4`

**Interfaces:**
- Consumes: cached S1E1 analysis and the corrected renderer.
- Produces: four replaced portrait clips with synchronized safe-zone captions at 1.10×.

- [x] Re-render S1E1 using existing analysis, Ollama ranking, bold captions, and playback speed 1.10.
- [x] Use ffprobe to verify 1080×1920, SAR 1:1, DAR 9:16, and duration near source duration divided by 1.10.
- [x] Inspect full-resolution frames at long-caption moments and confirm no glyph crosses the portrait safe bounds.
- [x] Run Ruff, mypy, the complete pytest suite, and the browser smoke test.
