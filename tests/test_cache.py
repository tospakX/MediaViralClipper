from pathlib import Path

from clipper.cache import StageCache, clear_stage_caches, fingerprint


def test_cache_round_trip_is_deterministic(tmp_path: Path) -> None:
    cache = StageCache(tmp_path)
    key = fingerprint({"source": "episode.mkv", "size": 12})

    cache.save("probe", key, {"z": 1, "a": [2, 3]})

    assert cache.load("probe", key) == {"a": [2, 3], "z": 1}
    raw = (tmp_path / "probe.json").read_text(encoding="utf-8")
    assert raw.index('"a"') < raw.index('"z"')


def test_cache_rejects_a_stale_fingerprint(tmp_path: Path) -> None:
    cache = StageCache(tmp_path)
    cache.save("transcript", "old", {"segments": []})

    assert cache.load("transcript", "new") is None


def test_source_fingerprint_changes_with_stat(tmp_path: Path) -> None:
    source = tmp_path / "episode.mkv"
    source.write_bytes(b"one")
    first = StageCache.source_fingerprint(source)
    source.write_bytes(b"different-size")

    assert StageCache.source_fingerprint(source) != first


def test_clear_stage_caches_preserves_finished_exports(tmp_path: Path) -> None:
    cache = tmp_path / "Season 01" / "Episode 01" / ".cache"
    cache.mkdir(parents=True)
    (cache / "transcript.json").write_text("cached")
    clip = cache.parent / "clip_01"
    clip.mkdir()
    export = clip / "vertical.mp4"
    export.write_bytes(b"finished-video")

    removed = clear_stage_caches(tmp_path)

    assert removed == (cache,)
    assert not cache.exists()
    assert export.read_bytes() == b"finished-video"
