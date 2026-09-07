import asyncio

import httpx

from clipper.web import create_app
from clipper.web_jobs import JobManager


def _get(path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(JobManager()))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            return await client.get(path)

    return asyncio.run(request())


def test_home_exposes_an_accessible_batch_workflow() -> None:
    response = _get("/")

    assert response.status_code == 200
    assert '<form id="job-form"' in response.text
    assert '<label for="source">' in response.text
    assert '<label for="output">' in response.text
    assert 'type="submit"' in response.text
    assert 'aria-live="polite"' in response.text
    assert 'id="results"' in response.text
    assert 'id="episode-list"' in response.text


def test_home_uses_automatic_clip_selection_and_a_visual_file_browser() -> None:
    response = _get("/")

    assert 'name="clips"' not in response.text
    assert "Auto clip count" in response.text
    assert 'id="select-folder"' in response.text
    assert 'id="select-video"' in response.text
    assert 'id="file-browser"' in response.text
    assert "Use this folder" in response.text


def test_home_has_explicit_batch_ingest_queue_tools_and_preview_stage() -> None:
    response = _get("/")

    assert 'id="select-folder"' in response.text
    assert 'id="select-video"' in response.text
    assert 'id="queue-search"' in response.text
    assert 'id="queue-filter"' in response.text
    assert 'id="preview-player"' in response.text
    assert 'id="clip-strip"' in response.text
    assert 'id="previous-cuts"' not in response.text
    assert "Previous cuts" not in response.text


def test_preview_hides_transcript_by_default_and_has_review_navigation() -> None:
    response = _get("/")

    assert 'id="transcript-toggle"' in response.text
    assert 'aria-expanded="false"' in response.text
    assert 'id="preview-transcript" class="transcript" hidden' in response.text
    assert 'id="previous-clip"' in response.text
    assert 'id="next-clip"' in response.text


def test_preview_is_portrait_first_and_ollama_is_the_default_judge() -> None:
    response = _get("/")

    assert 'class="player-shell" data-format="vertical"' in response.text
    assert '<option value="ollama" selected>Ollama · Qwen 1.7B</option>' in response.text
    assert "Strict 9:16" in response.text


def test_batch_ui_explains_folder_limit_and_sequential_processing() -> None:
    response = _get("/")

    assert "folder containing up to 100" in response.text
    assert "process one at a time" in response.text
    assert "~/Downloads/MediaViralClipper" in response.text


def test_frontend_assets_are_local_and_never_stale() -> None:
    page = _get("/")
    stylesheet = _get("/assets/app.css")
    script = _get("/assets/app.js")

    assert 'href="/assets/app.css"' in page.text
    assert 'src="/assets/app.js"' in page.text
    assert "https://" not in page.text
    assert stylesheet.status_code == 200
    assert stylesheet.headers["cache-control"] == "no-store"
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert script.headers["cache-control"] == "no-store"
    assert (
        "application/javascript" in script.headers["content-type"]
        or "text/javascript" in script.headers["content-type"]
    )


def test_advanced_controls_cover_quality_and_performance_choices() -> None:
    response = _get("/")

    assert 'name="caption_style"' in response.text
    assert 'name="whisper_model"' in response.text
    assert 'name="hardware_encoding"' in response.text
    assert 'name="workers"' in response.text
    assert 'name="dry_run"' in response.text
