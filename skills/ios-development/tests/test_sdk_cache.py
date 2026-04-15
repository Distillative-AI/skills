"""Functional tests for the 24h SDK cache."""
import json
import time
from pathlib import Path

from app.sdk_cache import CACHE_TTL_SECONDS, SDKCache, SDKManifest


def test_get_creates_cache_when_missing(tmp_path):
    cache = SDKCache(cache_dir=tmp_path)
    manifest = cache.get()
    assert (tmp_path / "sdks.json").exists()
    # We may be in a CI environment without xcrun; either source is valid.
    assert manifest.source in {"xcodebuild", "fallback"}


def test_get_returns_cached_when_fresh(tmp_path):
    cache = SDKCache(cache_dir=tmp_path)
    first = cache.get()
    second = cache.get()
    assert first.fetched_at == second.fetched_at, "should not refresh while fresh"


def test_get_refreshes_when_stale(tmp_path):
    cache = SDKCache(cache_dir=tmp_path)
    stale = SDKManifest(fetched_at=time.time() - CACHE_TTL_SECONDS - 60)
    (tmp_path / "sdks.json").write_text(stale.to_json())
    refreshed = cache.get()
    assert refreshed.fetched_at > stale.fetched_at


def test_invalidate_removes_cache_file(tmp_path):
    cache = SDKCache(cache_dir=tmp_path)
    cache.get()
    assert (tmp_path / "sdks.json").exists()
    cache.invalidate()
    assert not (tmp_path / "sdks.json").exists()


def test_manifest_round_trip():
    m = SDKManifest(fetched_at=1234.5, latest_ios="18.0")
    decoded = SDKManifest.from_json(m.to_json())
    assert decoded.latest_ios == "18.0"
    assert decoded.fetched_at == 1234.5


def test_ttl_is_24_hours():
    assert CACHE_TTL_SECONDS == 24 * 60 * 60
