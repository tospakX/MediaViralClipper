# Media Viral Clipper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, resumable pipeline that finds, ranks, refines, and exports 2–3 coherent funny or engaging short-form clips from a supplied video.

**Architecture:** A typed Python package orchestrates immutable JSON stage artifacts: probe, transcript, scenes/audio, candidates, ranking, selections, and renders. Heavy integrations (FFmpeg, embedded subtitles, faster-whisper, PySceneDetect/OpenCV, optional LLM providers) sit behind small adapters; deterministic heuristic fallbacks keep the pipeline usable and testable without cloud services. Rendering uses FFmpeg for source-aspect clips and captions, while a sampled OpenCV subject/saliency tracker writes a smooth time-varying crop path for 1080x1920 output.

**Tech Stack:** Python 3.11–3.13, Pydantic 2, Typer, Rich, FFmpeg/ffprobe, faster-whisper, PySceneDetect, OpenCV, NumPy, pytest, Ruff, mypy.

**Spec:** `/home/tospak/.codex/attachments/d4cadcd0-7171-459d-99ba-96c7c6e2d922/pasted-text-1.txt`

## Global Constraints

- Create only `/home/tospak/Desktop/Code/MediaViralClipper`; never modify `/home/tospak/Desktop/Code/clipAuto`.
- Default clip duration is 15–40 seconds; never exceed 40 seconds unless configured explicitly.
- Prefer embedded subtitles, fall back to local faster-whisper, and send no video to an LLM.
- Default output includes source-aspect and optional 1080x1920 vertical files, SRT, per-clip metadata, ranking, and transcript.
- Preserve source media; stage failures are isolated, cached work is reusable, and JSON output is deterministic.
- Do not commit or push.

---

### Task 1: Package foundation, data contracts, configuration, and cache

**Files:**
- Create: `pyproject.toml`, `README.md`, `.gitignore`
- Create: `src/clipper/__init__.py`, `src/clipper/models.py`, `src/clipper/config.py`, `src/clipper/timecode.py`, `src/clipper/cache.py`
- Test: `tests/test_config.py`, `tests/test_timecode.py`, `tests/test_cache.py`

**Interfaces:**
- Produces: validated `ClipperConfig`; serializable `MediaInfo`, `TranscriptSegment`, `Scene`, `Candidate`, `Score`, and `Selection`; `StageCache.load/save/is_valid`; timestamp/SRT formatting helpers.

- [ ] Write behavior-first tests for duration validation, configurable hard limits, timestamp conversion, deterministic atomic cache records, and fingerprint invalidation.
- [ ] Run those tests and confirm they fail because the package does not exist.
- [ ] Implement only the contracts and helpers required by the tests.
- [ ] Run the focused tests and full suite until green; run Ruff and mypy on the new modules.

### Task 2: Media analysis adapters

**Files:**
- Create: `src/clipper/process.py`, `src/clipper/media.py`, `src/clipper/transcription.py`, `src/clipper/scenes.py`, `src/clipper/audio.py`
- Test: `tests/test_media.py`, `tests/test_transcription.py`, `tests/test_analysis.py`

**Interfaces:**
- Consumes: `ClipperConfig`, stage cache, model contracts.
- Produces: `probe_media(path) -> MediaInfo`; `transcribe(path, media, config) -> list[TranscriptSegment]`; `detect_scenes(...) -> list[Scene]`; audio activity/intensity intervals; safe argv-only subprocess execution.

- [ ] Write tests using literal ffprobe/subtitle fixtures and a generated WAV/video fixture; verify embedded subtitle preference, sentence-preserving normalization, scene fallback, and safe filenames.
- [ ] Run focused tests and observe expected failures.
- [ ] Implement ffprobe/FFmpeg adapters, embedded SRT/ASS extraction, lazy faster-whisper integration, PySceneDetect integration with deterministic fallback, and audio analysis.
- [ ] Run focused and full tests; lint and type-check.

### Task 3: Candidate generation, ranking, diversity, and boundary refinement

**Files:**
- Create: `src/clipper/candidates.py`, `src/clipper/ranking.py`, `src/clipper/providers.py`, `src/clipper/refine.py`
- Test: `tests/test_candidates.py`, `tests/test_ranking.py`, `tests/test_refine.py`

**Interfaces:**
- Produces: transcript/scene-aware `generate_candidates`; feature-based `HeuristicRanker`; JSON-protocol `OpenAICompatibleRanker`; weighted score aggregation; MMR-like non-overlap/diversity selection; sentence/pause-aware `refine_boundary` enforcing the hard limit.

- [ ] Write tests for minimum/maximum duration, complete sentence boundaries, punchline/hook weighting, overlap/adjacency suppression, topic diversity, and the absolute duration cap.
- [ ] Run focused tests and observe expected failures.
- [ ] Implement generation, deterministic heuristic scoring, swappable provider protocol, diversity selection, and refinement.
- [ ] Run focused and full tests; lint and type-check.

### Task 4: Captions, subject-aware reframing, and resilient rendering

**Files:**
- Create: `src/clipper/subtitles.py`, `src/clipper/reframe.py`, `src/clipper/render.py`
- Test: `tests/test_subtitles.py`, `tests/test_reframe.py`, `tests/test_render.py`

**Interfaces:**
- Produces: short caption cues and SRT/ASS; smoothed crop keyframes from faces, motion, and saliency; FFmpeg filter graphs; per-clip render results that retain other successful clips when one fails.

- [ ] Write tests for cue chunking/punctuation, punchline emphasis metadata, caption safe zones, crop clamping/smoothing, 1080x1920 filter construction, argv safety, and isolated failures.
- [ ] Run focused tests and observe expected failures.
- [ ] Implement caption generation, OpenCV tracker with center fallback, time-varying crop expressions, hardware encoder detection/fallback, and render orchestration.
- [ ] Run focused and full tests; lint and type-check.

### Task 5: Resumable pipeline and output contract

**Files:**
- Create: `src/clipper/pipeline.py`, `src/clipper/state.py`, `tests/test_pipeline.py`, `tests/test_output.py`

**Interfaces:**
- Produces: `ClipperPipeline.run(source, dry_run)` with cached stage manifests and the required `output/<episode>/clip_NN` hierarchy, `ranking.json`, `transcript.json`, and complete `metadata.json`.

- [ ] Write integration tests for output naming, deterministic reruns, cache reuse, dry-run render omission, and continuation after one render error.
- [ ] Run focused tests and observe expected failures.
- [ ] Implement the orchestrator and state transitions with atomic writes and per-stage fingerprints.
- [ ] Run focused and full tests; lint and type-check.

### Task 6: CLI, progress, structured logs, and documentation

**Files:**
- Create: `src/clipper/__main__.py`, `src/clipper/cli.py`, `src/clipper/logging.py`, `tests/test_cli.py`
- Modify: `README.md`, `pyproject.toml`

**Interfaces:**
- Produces: `python -m clipper VIDEO` with `--clips`, `--min-duration`, `--max-duration`, `--vertical/--no-vertical`, `--captions/--no-captions`, `--output`, `--dry-run`, model/device/provider options, Rich progress, and JSONL logs.

- [ ] Write CLI tests for help, validation, dry-run forwarding, filenames with spaces, and nonzero failure exits.
- [ ] Run focused tests and observe expected failures.
- [ ] Implement CLI/config merging, progress events, logs, installation groups, and full setup/usage/provider documentation.
- [ ] Run focused and full tests; lint, type-check, and execute `python -m clipper --help`.

### Task 7: Synthetic end-to-end fixture and final verification

**Files:**
- Create: `tests/fixtures/transcript.srt`, `tests/test_e2e.py`
- Modify: `README.md`

**Interfaces:**
- Verifies all preceding public contracts against a tiny FFmpeg-generated, non-copyrighted video.

- [ ] Write an end-to-end test that generates color/test-pattern scenes and tone/silence, injects synthetic dialogue subtitles, runs dry-run plus render, and validates media dimensions/durations and JSON fields.
- [ ] Run it before final integration and confirm any missing behavior fails visibly.
- [ ] Complete only missing behavior exposed by the test, then rerun it.
- [ ] Run the full test suite, Ruff, mypy, package build/syntax checks, CLI help, and a real dry-run if any local sample is available.
- [ ] Compare final files and behavior line-by-line with the source spec; document exact install and 20-minute episode commands without committing or pushing.

## Self-review

The tasks cover probing/transcription/scenes/audio, candidate generation, dialogue-led scoring and provider swapping, diversity, sentence-safe refinement, both render formats, saliency-aware tracking, captions/SRT, the complete output contract, CLI options, caching/resume/failure isolation, CPU/GPU controls, tests, and final verification. No placeholder implementation tasks remain; names and stage artifacts are consistent across tasks.
