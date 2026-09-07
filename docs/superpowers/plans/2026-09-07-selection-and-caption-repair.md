# Selection and Caption Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return only one to three genuinely distinct episode moments and render stable, correctly segmented portrait subtitles.

**Architecture:** Strengthen temporal-storyline diversity and automatic count policy in `ranking.py`, keeping the hard 40-second clip boundary intact. Repair caption segmentation at dialogue-turn boundaries and remove active-word scaling that changes line wrapping from frame to frame while retaining color emphasis.

**Tech Stack:** Python 3.12, Pydantic, FFmpeg/libass, pytest, Ollama.

**Spec:** Current user report against the generated S1E1 clips: clips 1 and 4 represent one storyline, four outputs are excessive, and subtitles visibly break.

## Global Constraints

- Automatic output count must be between one and three.
- Never combine material into an output longer than the configured 40-second maximum.
- Candidates from the same nearby story sequence must not occupy separate output slots.
- Caption lines must not combine two dash-prefixed dialogue turns.
- Active-word emphasis must not resize or reflow the caption.
- Preserve 1080×1920, 9:16 output and synchronized 1.10× playback.

---

### Task 1: Storyline Diversity and One-to-Three Count

**Files:**
- Modify: `src/clipper/ranking.py`
- Modify: `src/clipper/pipeline.py`
- Test: `tests/test_ranking.py`

**Interfaces:**
- Consumes: ranked `Candidate` values with start/end timestamps and scores.
- Produces: `choose_diverse(...)` without nearby duplicate story beats and `automatic_clip_count(...)` in the inclusive range 1–3.

- [x] Add a failing test in which two non-overlapping candidates separated by a 35-second gap compete for one storyline slot.
- [x] Add failing count tests requiring one weak viable moment and a hard maximum of three for long media.
- [x] Run `uv run pytest -q tests/test_ranking.py` and confirm policy failures.
- [x] Treat candidates separated by at most 45 seconds as one temporal story cluster.
- [x] Remove the pipeline's forced minimum of two similar selections and cap automatic count at three.
- [x] Run focused ranking and pipeline tests.

### Task 2: Stable Dialogue-Safe Captions

**Files:**
- Modify: `src/clipper/subtitles.py`
- Test: `tests/test_subtitles.py`

**Interfaces:**
- Consumes: `Word` sequences, including embedded-subtitle tokens whose leading dash marks a speaker change.
- Produces: cues that never mix speakers and ASS events whose active highlight changes color only.

- [x] Add a failing test proving `bildirmediniz? -Size` is split across separate cues.
- [x] Add a failing ASS test forbidding scale overrides that trigger frame-to-frame wrapping changes.
- [x] Run `uv run pytest -q tests/test_subtitles.py` and confirm both reproduce the current behavior.
- [x] Split chunks before a dash-prefixed speaker token and keep each cue within existing portrait width limits.
- [x] Remove active-word scaling and persistent long-word coloring, retaining one yellow active word and white inactive words.
- [x] Render and inspect real S1E1 frames across a caption transition.

### Task 3: End-to-End Regression and Release

**Files:**
- Modify: `README.md`
- Verify: `~/Downloads/MediaViralClipper/S1E1/clip_*/vertical.mp4`

**Interfaces:**
- Consumes: corrected selection/caption pipeline.
- Produces: one to three regenerated S1E1 clips and updated public repository.

- [x] Re-run S1E1 with automatic Ollama ranking and overwrite enabled.
- [x] Verify selected count is 1–3 and no pair is from the same 45-second story cluster.
- [x] Verify SRT speaker boundaries, ASS stability, 1080×1920 geometry, audio, and 1.10× duration.
- [x] Run Ruff, formatting, mypy, all tests, build, and browser smoke tests.
- [ ] Commit and push the verified repair to GitHub.
