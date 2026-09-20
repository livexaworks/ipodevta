"""Preview pool disk cache."""

import json
import time

from bot import preview_cache


def test_pool_cache_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "preview_pool.json"
    monkeypatch.setattr(preview_cache, "POOL_PATH", path)
    monkeypatch.setattr(preview_cache, "POOL_TTL_SEC", 3600)
    rows = [{"ipo_id": "A", "name": "Alpha", "gmp_pct": 30}]
    preview_cache.save_live_pool(rows)
    loaded = preview_cache.load_cached_live_pool(5)
    assert loaded is not None
    assert loaded[0]["ipo_id"] == "A"


def test_pool_cache_expired(tmp_path, monkeypatch):
    path = tmp_path / "preview_pool.json"
    monkeypatch.setattr(preview_cache, "POOL_PATH", path)
    monkeypatch.setattr(preview_cache, "POOL_TTL_SEC", 1)
    path.write_text(
        json.dumps({"ts": time.time() - 10, "ipos": [{"ipo_id": "X"}]}),
        encoding="utf-8",
    )
    assert preview_cache.load_cached_live_pool(5) is None
