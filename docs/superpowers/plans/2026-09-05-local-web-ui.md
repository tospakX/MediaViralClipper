# Local Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a responsive localhost UI that starts clip jobs, shows live pipeline progress, and previews/downloads ranked outputs without weakening the existing CLI.

**Architecture:** A small FastAPI server wraps the existing `ClipperPipeline` through a single-worker, thread-safe job manager. A dependency-free HTML/CSS/JavaScript client consumes JSON endpoints, polls job state, renders the real pipeline stages as a cut timeline, and presents playable result cards. Media serving resolves only known job artifacts, preventing arbitrary filesystem reads.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic, vanilla HTML/CSS/JavaScript, pytest/TestClient, Playwright.

**Spec:** User request dated 2026-09-05: “I want a simple localhost web ui. also make ts 100x better.”

## Global Constraints

- Keep the existing `python -m clipper VIDEO` CLI working.
- Bind to `127.0.0.1` by default; external binding must be explicit.
- Never expose arbitrary filesystem paths through download endpoints.
- Run at most one heavy pipeline job at a time by default.
- Preserve cached/resumable pipeline behavior and source media.
- Make the UI responsive, keyboard accessible, reduced-motion aware, and useful without external fonts or CDNs.
- Do not commit or push.

---

### Task 1: Web job contracts and bounded execution

**Files:**
- Create: `src/clipper/web_jobs.py`
- Test: `tests/test_web_jobs.py`

**Interfaces:**
- Produces: `WebJobRequest`, `JobSnapshot`, and `JobManager.start/get/close`; consumes `ClipperPipeline` through an injected factory and maps pipeline progress to stable percentages.

- [ ] Write failing tests proving invalid/missing sources are rejected, a job transitions through queued/running/completed, progress is monotonic, pipeline results are serialized, and one failure becomes a readable failed snapshot.
- [ ] Run `uv run pytest tests/test_web_jobs.py -q` and confirm failures name missing web job contracts.
- [ ] Implement the thread-safe single-worker manager and immutable response snapshots.
- [ ] Run the focused tests and the full suite.

### Task 2: Local API and constrained artifact serving

**Files:**
- Create: `src/clipper/web.py`
- Modify: `pyproject.toml`
- Test: `tests/test_web_api.py`

**Interfaces:**
- Produces: `create_app(manager=None) -> FastAPI`; `GET /api/health`; `POST /api/jobs`; `GET /api/jobs/{id}`; and `GET /api/jobs/{id}/clips/{rank}/{artifact}` for known outputs only.

- [ ] Write failing TestClient tests for home/health, request validation, job creation/status, unknown jobs, successful clip media, missing media, and artifact-name/path traversal rejection.
- [ ] Run the focused tests and confirm the routes are absent.
- [ ] Implement the API, static-resource routes, shutdown cleanup, localhost launcher, and `clipper-web` entry point.
- [ ] Run focused and full tests, Ruff, and mypy.

### Task 3: Cut-room frontend

**Files:**
- Create: `src/clipper/web_static/index.html`, `src/clipper/web_static/app.css`, `src/clipper/web_static/app.js`
- Test: `tests/test_web_ui.py`

**Interfaces:**
- Consumes: API contracts from Task 2.
- Produces: accessible job form, advanced settings disclosure, live stage timeline, failure/empty states, score meters, transcript cards, native video previews, and download links.

- [ ] Write failing UI contract tests that fetch the real document and verify accessible labels, submit semantics, status live region, stage names, result container, and local static assets.
- [ ] Run focused tests and observe the missing UI contract.
- [ ] Build the frontend from the cut-room token system: Frost `#EEF2F6`, Paper `#FFFFFF`, Ink `#13213C`, Cobalt `#315CFF`, Coral `#F0645A`, Tape `#F2C14E`; use `Arial Narrow`/`Aptos` display, system body, and `DejaVu Sans Mono` utility roles.
- [ ] Implement browser validation, API submission, resilient polling, progress/result rendering, preserved form settings, keyboard focus, and reduced-motion behavior.
- [ ] Run focused/full tests and lint checks.

### Task 4: Browser validation and documentation

**Files:**
- Modify: `README.md`
- Create: `tests/browser/browser_smoke.py`

**Interfaces:**
- Produces: documented `uv run clipper-web` startup and a Playwright smoke test against a real local server.

- [ ] Document install/start/use, localhost security, job lifecycle, dry-run behavior, and artifact preview/download behavior.
- [ ] Run the server helper with `--help`, then execute a headless Chromium test that checks desktop and mobile layout, form interaction, advanced controls, visible progress semantics, and absence of browser console errors.
- [ ] Capture and visually inspect desktop/mobile screenshots; revise hierarchy, overflow, contrast, focus, and copy issues found in the rendered UI.
- [ ] Run the complete pytest, Ruff, format, mypy, compile, package-build, CLI-help, web-health, and browser checks without committing or pushing.

## Self-review

This plan covers the requested localhost experience plus the quality multipliers that matter in actual use: bounded background work, live progress, strong validation, filesystem-safe media delivery, playable results, responsive/accessibility states, persistence of form choices, compatibility with the existing CLI, tests at service/API/browser layers, and operational documentation. The visual system is specific to video editing—the stage rail doubles as a cut timeline—and avoids CDN dependencies or generic dashboard ornament.
