# Ollama-First Vertical Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MediaViralClipper produce strict 9:16 Shorts, rank clips with the installed local Qwen Ollama model, and provide a simpler portrait-first review UI for large episode queues.

**Architecture:** Keep the existing staged pipeline, add a native Ollama ranker behind the provider interface with bounded shortlisting and heuristic fallback, normalize rendered sample aspect ratio, and make the web player derive its shape from the selected output format. Preserve resumability and batch safety.

**Tech Stack:** Python 3.12, Pydantic, FFmpeg/ffprobe, Ollama HTTP API, vanilla HTML/CSS/JavaScript, pytest, Playwright.

**Spec:** User request in current conversation

## Global Constraints

- [x] Do not modify or delete source videos.
- [x] Keep large queues resumable and prevent one Ollama/render failure from stopping other jobs.
- [x] Keep generated output under `~/Downloads/MediaViralClipper`.
- [x] Verify behavior with tests and the existing episode output before completion.

---

### Task 1: Enforce true 9:16 exports

**Files:** `tests/test_render.py`, `src/clipper/render.py`

- [x] Add a failing assertion for square-pixel vertical output.
- [x] Add `setsar=1` to the vertical video filter and version the render fingerprint.
- [x] Verify the generated filter and ffprobe geometry.

### Task 2: Make Ollama the primary local judge

**Files:** `tests/test_providers.py`, `tests/test_config.py`, `tests/test_web_jobs.py`, `src/clipper/providers.py`, `src/clipper/config.py`, `src/clipper/pipeline.py`, `src/clipper/web_jobs.py`, `src/clipper/cli.py`

- [x] Test the native Ollama request, structured response mapping, bounded shortlisting, and failure fallback.
- [x] Implement `OllamaRanker` for `qwen3:1.7b` without requiring an API key.
- [x] Make Ollama the default while retaining heuristic and OpenAI-compatible options.
- [x] Surface Ollama readiness in diagnostics without making queue processing brittle.

### Task 3: Replace the widescreen review experience

**Files:** `tests/test_web_ui.py`, `tests/browser/browser_smoke.py`, `src/clipper/web_static/index.html`, `src/clipper/web_static/app.css`, `src/clipper/web_static/app.js`

- [x] Add tests for a portrait-default player, format-aware aspect ratio, minimal controls, and hidden transcript.
- [x] Rework the selected clip into a centered 9:16 viewing frame with an explicit original/vertical switch.
- [x] Auto-open the newest finished cut and keep queue/folder actions suitable for 80–100 inputs.
- [x] Confirm responsive behavior and browser console cleanliness.

### Task 4: Full verification

- [x] Run focused unit tests, then the full test suite.
- [x] Run the browser smoke test at desktop and mobile sizes.
- [x] Re-render or probe a real episode cut and confirm 1080×1920, SAR 1:1, DAR 9:16.
- [x] Restart the local web server and verify Ollama/model status through the UI/API.
