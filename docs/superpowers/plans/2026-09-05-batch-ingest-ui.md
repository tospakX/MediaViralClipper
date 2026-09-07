# Batch Ingest UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-episode form with a simple file-or-folder workflow that safely queues up to 100 episodes and saves all output below `~/Downloads/MediaViralClipper`.

**Architecture:** Keep `JobManager` as the single-worker execution boundary and add a batch registry that groups normal jobs. A batch API discovers supported local media recursively, queues deterministic paths, and returns one aggregate snapshot so the browser does not poll 100 endpoints. The UI becomes a compact setup panel plus episode queue; full clip cards render only for a selected completed episode.

**Tech Stack:** Python 3.12, Pydantic, FastAPI, vanilla HTML/CSS/JavaScript, pytest, Playwright.

**Spec:** User request in this conversation on 2026-09-05.

## Global Constraints

- Accept one local media file or a directory containing up to 100 supported episodes.
- Never upload or copy source episodes through HTTP.
- Queue heavy processing sequentially.
- Default output to `~/Downloads/MediaViralClipper`.
- Keep controls and status understandable with 70–100 episodes.
- Preserve existing single-job and artifact APIs.
- Preserve keyboard access, mobile layout, and reduced-motion behavior.

---

### Task 1: Deterministic Batch Discovery

**Files:**
- Modify: `src/clipper/web_jobs.py`
- Test: `tests/test_web_jobs.py`

**Interfaces:**
- Produces: `discover_media_files(source: Path, limit: int = 100) -> tuple[Path, ...]`
- Produces: `WebBatchRequest.to_jobs() -> tuple[WebJobRequest, ...]`

- [ ] Write tests proving recursive, case-insensitive media discovery, stable ordering, the 100-file limit, ignored non-media files, and `~/Downloads/MediaViralClipper` as the output default.
- [ ] Run focused tests and confirm failures come from missing batch contracts.
- [ ] Add the batch request and discovery implementation with supported extensions `.mp4`, `.mkv`, `.mov`, `.webm`, `.m4v`, `.avi`.
- [ ] Run the focused tests until green.

### Task 2: Aggregate Batch Queue API

**Files:**
- Modify: `src/clipper/web_jobs.py`
- Modify: `src/clipper/web.py`
- Test: `tests/test_web_jobs.py`
- Test: `tests/test_web_api.py`

**Interfaces:**
- Produces: `JobManager.start_batch(request: WebBatchRequest) -> str`
- Produces: `JobManager.get_batch(batch_id: str) -> BatchSnapshot`
- Produces: `POST /api/batches` and `GET /api/batches/{batch_id}`

- [ ] Write tests proving a folder creates one sequential job per episode and aggregate counts/progress reflect its jobs.
- [ ] Write API tests proving invalid/oversized folders return actionable 422 responses and unknown batches return 404.
- [ ] Run focused tests and observe expected missing-interface failures.
- [ ] Implement the batch registry and endpoints by reusing ordinary jobs rather than introducing a second executor.
- [ ] Run focused tests until green.

### Task 3: Simple Batch-First Interface

**Files:**
- Modify: `src/clipper/web_static/index.html`
- Modify: `src/clipper/web_static/app.css`
- Modify: `src/clipper/web_static/app.js`
- Modify: `tests/browser/browser_smoke.py`

**Interfaces:**
- Consumes: batch create/snapshot endpoints from Task 2.
- Produces: one file-or-folder form, aggregate progress, scalable episode rows, and on-demand selected episode clip details.

- [ ] Update the browser smoke test to exercise a folder batch and assert queue rows, aggregate completion, selected results, output default, mobile width, and zero console errors.
- [ ] Run it against the current UI and confirm it fails on the missing batch behavior.
- [ ] Replace promotional copy and multi-panel clutter with the ingest desk, collapsed advanced controls, and a compact queue.
- [ ] Implement one aggregate polling request, persisted last batch ID, and lazy clip-card rendering when a completed episode row is selected.
- [ ] Run desktop and mobile Playwright checks, inspect screenshots, and remove nonessential decoration.

### Task 4: Documentation and Full Verification

**Files:**
- Modify: `README.md`

**Interfaces:**
- Documents: file-or-folder workflow, 100-episode limit, sequential processing, and output location.

- [ ] Update the localhost UI instructions and output tree.
- [ ] Run all pytest, Ruff, formatting, mypy, compile, JavaScript syntax, package-build, system-doctor, synthetic render, and Playwright checks.
- [ ] Confirm `~/Downloads/MediaViralClipper` exists and is writable without touching `~/Downloads/Explained.Summary`.
