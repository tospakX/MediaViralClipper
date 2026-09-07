import asyncio
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from clipper.config import ClipperConfig
from clipper.models import Candidate, RenderResult, Score, Selection
from clipper.pipeline import PipelineResult
from clipper.web import create_app
from clipper.web_jobs import JobManager


def _request(
    app: FastAPI, method: str, path: str, json: dict[str, Any] | None = None
) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            return await client.request(method, path, json=json)

    return asyncio.run(send())


def _manager(tmp_path: Path) -> JobManager:
    class FakePipeline:
        def __init__(self, config: ClipperConfig, progress: object) -> None:
            self.config = config

        def run(self, source: Path, dry_run: bool) -> PipelineResult:
            output = self.config.output.resolve() / "episode"
            clip = output / "clip_01"
            clip.mkdir(parents=True, exist_ok=True)
            original = clip / "original.mp4"
            original.write_bytes(b"synthetic-video")
            (clip / "metadata.json").write_text('{"rank": 1}', encoding="utf-8")
            candidate = Candidate(
                id="one",
                start=1,
                end=21,
                transcript="A complete setup. A cleaner punchline!",
                segment_indices=(0, 1),
            )
            score = Score(
                humor=0.9,
                punchline=0.9,
                surprise=0.8,
                quotability=0.75,
                hook=0.85,
                standalone=0.8,
                pacing=0.75,
                reaction=0.7,
                retention=0.82,
                overall=0.85,
                explanation="The exchange lands without outside context.",
            )
            return PipelineResult(
                source=source,
                episode_directory=output,
                dry_run=dry_run,
                selections=(Selection(rank=1, candidate=candidate, score=score),),
                renders=(RenderResult(clip=1, original=original),) if not dry_run else (),
            )

    return JobManager(pipeline_factory=FakePipeline)


def test_home_and_health_are_local_app_endpoints(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    app = create_app(manager)

    home = _request(app, "GET", "/")
    health = _request(app, "GET", "/api/health")
    manager.close()

    assert home.status_code == 200
    assert "Media Viral Clipper" in home.text
    assert health.json() == {"status": "ok", "scope": "localhost"}
    assert health.headers["cache-control"] == "no-store"


def test_server_startup_and_shutdown_clear_cache_but_keep_exports(tmp_path: Path) -> None:
    output = tmp_path / "MediaViralClipper"
    cache = output / "episode" / ".cache"
    cache.mkdir(parents=True)
    (cache / "old.json").write_text("old")
    export = output / "episode" / "clip_01" / "vertical.mp4"
    export.parent.mkdir()
    export.write_bytes(b"finished")
    app = create_app(startup_cache_root=output)

    async def run_lifecycle() -> None:
        async with app.router.lifespan_context(app):
            assert not cache.exists()
            cache.mkdir()
            (cache / "new.json").write_text("new")

    asyncio.run(run_lifecycle())

    assert not cache.exists()
    assert export.read_bytes() == b"finished"


def test_system_endpoint_exposes_episode_readiness(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    expected = {"ready": True, "checks": [], "summary": "Ready for an episode"}
    app = create_app(manager, system_inspector=lambda: expected)

    response = _request(app, "GET", "/api/system")
    manager.close()

    assert response.status_code == 200
    assert response.json() == expected
    assert response.headers["cache-control"] == "no-store"


def test_home_contains_live_system_readiness_badge(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    app = create_app(manager)

    home = _request(app, "GET", "/")
    manager.close()

    assert 'id="system-badge"' in home.text
    assert 'id="system-label"' in home.text


def test_file_browser_lists_folders_and_supported_episodes(tmp_path: Path) -> None:
    library = tmp_path / "Season 01"
    library.mkdir()
    (library / "Episode 01.mkv").touch()
    (library / "notes.txt").touch()
    (library / "Extras").mkdir()
    manager = _manager(tmp_path)
    app = create_app(manager)

    response = _request(app, "GET", f"/api/files?path={library}")
    manager.close()

    assert response.status_code == 200
    assert response.json() == {
        "path": str(library.resolve()),
        "parent": str(tmp_path.resolve()),
        "directories": [{"name": "Extras", "path": str((library / "Extras").resolve())}],
        "files": [{"name": "Episode 01.mkv", "path": str((library / "Episode 01.mkv").resolve())}],
    }


def test_source_scan_counts_nested_episodes_before_queueing(tmp_path: Path) -> None:
    library = tmp_path / "Show"
    (library / "Season 01").mkdir(parents=True)
    (library / "Season 02").mkdir()
    (library / "Season 01" / "E01.mkv").touch()
    (library / "Season 02" / "E02.mp4").touch()
    manager = _manager(tmp_path)
    app = create_app(manager)

    response = _request(app, "GET", f"/api/scan?path={library}")
    manager.close()

    assert response.status_code == 200
    assert response.json() == {
        "path": str(library.resolve()),
        "total": 2,
        "kind": "folder",
        "sample": ["Season 01/E01.mkv", "Season 02/E02.mp4"],
    }


def test_library_restores_completed_clips_and_serves_preview(tmp_path: Path) -> None:
    output = tmp_path / "MediaViralClipper"
    clip = output / "Season 01" / "Episode 01" / "clip_01"
    clip.mkdir(parents=True)
    preview = clip / "vertical.mp4"
    preview.write_bytes(b"preview-video")
    (clip / "original.mp4").write_bytes(b"original-video")
    (clip / "subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    (clip / "metadata.json").write_text(
        '{"rank":1,"duration":24.5,"transcript":"Hello there.",'
        '"overall":0.87,"explanation":"Strong hook.","files":{"error":null}}',
        encoding="utf-8",
    )
    manager = _manager(tmp_path)
    app = create_app(manager)

    library = _request(app, "GET", f"/api/library?output={output}")
    artifact = _request(
        app,
        "GET",
        f"/api/library/artifact?output={output}&episode=Season%2001%2FEpisode%2001&rank=1&artifact=vertical",
    )
    manager.close()

    assert library.status_code == 200
    assert library.json()["episodes"][0]["id"] == "Season 01/Episode 01"
    assert library.json()["episodes"][0]["clips"][0] == {
        "rank": 1,
        "duration": 24.5,
        "overall": 0.87,
        "transcript": "Hello there.",
        "explanation": "Strong hook.",
        "original": True,
        "vertical": True,
        "subtitles": True,
    }
    assert artifact.status_code == 200
    assert artifact.content == b"preview-video"


def test_job_api_starts_and_returns_real_result_contract(tmp_path: Path) -> None:
    source = tmp_path / "episode with spaces.mkv"
    source.write_bytes(b"media")
    manager = _manager(tmp_path)
    app = create_app(manager)

    created = _request(
        app,
        "POST",
        "/api/jobs",
        json={"source": str(source), "output": str(tmp_path / "output"), "clips": 2},
    )
    job_id = created.json()["id"]
    manager.wait(job_id, timeout=2)
    result = _request(app, "GET", f"/api/jobs/{job_id}")
    manager.close()

    assert created.status_code == 202
    assert result.status_code == 200
    payload = result.json()
    assert payload["status"] == "completed"
    assert payload["selections"][0]["score"]["overall"] == 0.85
    assert payload["selections"][0]["candidate"]["transcript"].endswith("punchline!")


def test_media_endpoint_serves_only_known_job_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"media")
    manager = _manager(tmp_path)
    app = create_app(manager)
    created = _request(
        app,
        "POST",
        "/api/jobs",
        json={"source": str(source), "output": str(tmp_path / "output")},
    )
    job_id = created.json()["id"]
    manager.wait(job_id, timeout=2)

    media = _request(app, "GET", f"/api/jobs/{job_id}/clips/1/original")
    download = _request(app, "GET", f"/api/jobs/{job_id}/clips/1/original?download=true")
    metadata = _request(app, "GET", f"/api/jobs/{job_id}/clips/1/metadata")
    unknown = _request(app, "GET", f"/api/jobs/{job_id}/clips/1/source")
    traversal = _request(app, "GET", f"/api/jobs/{job_id}/clips/1/..%2F..%2Fetc%2Fpasswd")
    manager.close()

    assert media.status_code == 200
    assert media.content == b"synthetic-video"
    assert "content-disposition" not in media.headers
    assert download.headers["content-disposition"].startswith("attachment;")
    assert metadata.json() == {"rank": 1}
    assert unknown.status_code == 404
    assert traversal.status_code == 404


def test_unknown_job_and_missing_source_return_actionable_status(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    app = create_app(manager)

    unknown = _request(app, "GET", "/api/jobs/not-a-job")
    invalid = _request(
        app,
        "POST",
        "/api/jobs",
        json={"source": str(tmp_path / "missing.mkv"), "output": "output"},
    )
    manager.close()

    assert unknown.status_code == 404
    assert invalid.status_code == 422
    assert "source does not exist" in invalid.text


def test_batch_api_queues_a_folder_and_returns_aggregate_snapshot(tmp_path: Path) -> None:
    library = tmp_path / "Episodes"
    library.mkdir()
    (library / "episode-2.mkv").write_bytes(b"media")
    (library / "episode-1.mp4").write_bytes(b"media")
    manager = _manager(tmp_path)
    app = create_app(manager)

    created = _request(app, "POST", "/api/batches", json={"source": str(library)})
    batch_id = created.json()["id"]
    initial = _request(app, "GET", f"/api/batches/{batch_id}")
    for job in initial.json()["jobs"]:
        manager.wait(job["id"], timeout=2)
    finished = _request(app, "GET", f"/api/batches/{batch_id}")
    manager.close()

    assert created.status_code == 202
    assert created.json()["total"] == 2
    assert finished.json()["completed"] == 2
    assert finished.json()["progress"] == 100


def test_batch_api_rejects_oversized_folder_and_unknown_batch(tmp_path: Path) -> None:
    library = tmp_path / "Episodes"
    library.mkdir()
    for index in range(101):
        (library / f"episode-{index:03d}.mkv").touch()
    manager = _manager(tmp_path)
    app = create_app(manager)

    oversized = _request(app, "POST", "/api/batches", json={"source": str(library)})
    unknown = _request(app, "GET", "/api/batches/not-a-batch")
    manager.close()

    assert oversized.status_code == 422
    assert "batch limit is 100" in oversized.text
    assert unknown.status_code == 404
