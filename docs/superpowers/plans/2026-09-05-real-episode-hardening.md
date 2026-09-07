# Real Episode Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the first real 20-minute episode run reliable, efficient, and diagnosable before user testing.

**Architecture:** Harden optional media-analysis boundaries with explicit degradation paths, improve subtitle and sentence selection at the source, narrow cache fingerprints to stage-owned inputs, and expose a read-only system doctor through CLI and web UI. Preserve the existing modular pipeline, output contract, and localhost workflow.

**Tech Stack:** Python 3.12, FFmpeg/ffprobe, faster-whisper/CTranslate2, PySceneDetect, OpenCV, FastAPI, pytest, Playwright.

**Spec:** User request dated 2026-09-05: optimize it, make it better, and verify it before testing with an episode.

## Global Constraints

- Preserve existing CLI/web commands and output compatibility.
- Never hide source corruption as a benign missing optional stream.
- Auto-selected acceleration may fall back; explicitly requested CUDA/NVENC must still report failures.
- Sentence normalization must preserve timestamps, punctuation, words, and deterministic indexes.
- Cache invalidation must include every stage input and exclude unrelated downstream render settings.
- Do not commit or push.

---

### Task 1: Optional-analysis failure boundaries

**Files:**
- Modify: `src/clipper/audio.py`, `src/clipper/scenes.py`, `src/clipper/transcription.py`, `src/clipper/pipeline.py`
- Test: `tests/test_analysis.py`, `tests/test_transcription.py`, `tests/test_pipeline.py`

**Interfaces:**
- Produces: no-audio empty analysis, scene-detector fallback, and auto-CUDA-to-CPU Whisper retry while preserving explicit-device failures.

- [ ] Add failing tests reproducing the observed silent-media FFmpeg error, detector runtime error, CUDA model initialization failure, and no-audio pipeline path.
- [ ] Run focused tests and confirm each fails at the observed boundary.
- [ ] Implement narrow error classification and fallback behavior.
- [ ] Run focused/full tests and real silent-media smoke checks.

### Task 2: Embedded subtitle and sentence quality

**Files:**
- Modify: `src/clipper/models.py`, `src/clipper/media.py`, `src/clipper/transcription.py`, `src/clipper/candidates.py`
- Test: `tests/test_media.py`, `tests/test_transcription.py`, `tests/test_candidates.py`

**Interfaces:**
- Produces: `SubtitleTrack` metadata, language/default/full-track preference, coverage-based rejection of forced snippets, merged sentence segments, and safe candidate starts.

- [ ] Add failing tests for forced-first/full-second tracks, requested language preference, fragmented cues, long pauses, and lowercase mid-sentence starts.
- [ ] Run focused tests and confirm current selection/generation behavior fails.
- [ ] Implement deterministic track scoring and sentence merging before candidate generation.
- [ ] Run focused/full tests and a multi-track synthetic dry-run.

### Task 3: Cache and render efficiency

**Files:**
- Modify: `src/clipper/pipeline.py`, `src/clipper/render.py`
- Test: `tests/test_pipeline.py`, `tests/test_render.py`

**Interfaces:**
- Produces: stage-specific candidate fingerprints, per-run encoder capability reuse, render-start progress, and warning-free adaptive AAC quality.

- [ ] Add failing tests proving render-only settings do not invalidate candidates, encoder probing happens once per multi-clip run, render emits a started state, and audio encoding avoids fixed invalid bitrates.
- [ ] Run focused tests and observe the redundant/incorrect current behavior.
- [ ] Implement the smallest stage ownership and render-session changes.
- [ ] Run focused/full tests and compare cached rerun timing.

### Task 4: System doctor and UI readiness

**Files:**
- Create: `src/clipper/doctor.py`, `tests/test_doctor.py`
- Modify: `src/clipper/web.py`, `src/clipper/web_static/index.html`, `src/clipper/web_static/app.js`, `README.md`, `pyproject.toml`
- Test: `tests/test_web_api.py`, `tests/test_web_ui.py`

**Interfaces:**
- Produces: `clipper-doctor`, `GET /api/system`, and an honest UI readiness badge covering FFmpeg, subtitle rendering, local analysis imports, CUDA capability, NVENC, and free output space.

- [ ] Add failing unit/API/UI tests for required versus optional checks and machine-readable status.
- [ ] Implement read-only checks with timeouts and no model download.
- [ ] Render readiness without blocking job submission when only optional acceleration is unavailable.
- [ ] Run the doctor, API/browser smoke, full tests, lint/type/syntax/build checks, and synthetic render/dry-run verification.

## Self-review

The plan directly addresses every reproduced pre-episode risk, distinguishes optional acceleration from required tooling, improves selection quality without introducing a cloud dependency, and measures success through real FFmpeg, API, browser, cache, and pipeline behavior. It adds no unrelated feature surface and preserves source safety and prior commands.
