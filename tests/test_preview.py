"""Preview of recent / live IPOs for filter testing."""

from bot import preview, state


def test_latest_unique_snapshots_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(state.config, "SNAPSHOTS_PATH", tmp_path / "snapshots.json")
    assert preview._latest_unique_snapshots(5) == []


def test_latest_unique_keeps_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(state.config, "SNAPSHOTS_PATH", tmp_path / "snapshots.json")
    state.save_snapshots(
        [
            {
                "ipo_id": "A",
                "name": "Alpha",
                "date": "2026-09-18",
                "ts": "t1",
                "gmp_pct": 20,
                "board": "MAIN",
            },
            {
                "ipo_id": "A",
                "name": "Alpha",
                "date": "2026-09-19",
                "ts": "t2",
                "gmp_pct": 28,
                "board": "MAIN",
            },
            {
                "ipo_id": "B",
                "name": "Beta",
                "date": "2026-09-19",
                "ts": "t3",
                "gmp_pct": 10,
                "board": "MAIN",
            },
        ]
    )
    rows = preview._latest_unique_snapshots(5)
    assert len(rows) == 2
    assert rows[0]["ipo_id"] == "B" or rows[0]["gmp_pct"] in (28, 10)
    by_id = {r["ipo_id"]: r for r in rows}
    assert by_id["A"]["gmp_pct"] == 28


def test_build_preview_from_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(state.config, "SNAPSHOTS_PATH", tmp_path / "snapshots.json")
    state.save_snapshots(
        [
            {
                "ipo_id": "X1",
                "name": "Example One Ltd",
                "date": "2026-09-18",
                "ts": "a",
                "board": "MAIN",
                "gmp_pct": 30,
                "gmp": 50,
                "price_high": 100,
                "confidence": "high",
                "n_sources": 2,
                "spread_pct": 1,
                "sub_total": 3.0,
                "sub_qib": 2.0,
                "sub_nii": 4.0,
                "sub_retail": 3.0,
            },
            {
                "ipo_id": "X1",
                "name": "Example One Ltd",
                "date": "2026-09-19",
                "ts": "b",
                "board": "MAIN",
                "gmp_pct": 32,
                "gmp": 52,
                "price_high": 100,
                "confidence": "high",
                "n_sources": 2,
                "spread_pct": 1,
                "sub_total": 4.0,
                "sub_qib": 2.5,
                "sub_nii": 5.0,
                "sub_retail": 3.5,
            },
        ]
    )
    prefs = {
        "min_gmp_pct": 24.0,
        "min_total_sub": 1.0,
        "include_sme": False,
    }
    source, items = preview.build_preview(prefs, limit=5)
    assert source == "processed"
    assert len(items) == 1
    ipo, ok, reasons, prev, _live = items[0]
    assert ipo["name"].startswith("Example")
    assert prev is not None
    assert ok is True
    assert reasons == []
