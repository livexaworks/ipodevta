"""Flat sent.json keys: brief:{user}:{date} and channel:{date}."""

from bot import state


def test_brief_idempotency_keys(tmp_path, monkeypatch):
    path = tmp_path / "sent.json"
    monkeypatch.setattr(state.config, "SENT_PATH", path)
    assert state.brief_already_sent("2026-10-05", "111") is False
    state.mark_brief_sent("2026-10-05", "111", ipo_ids=["a"], quiet=True)
    assert state.brief_already_sent("2026-10-05", "111") is True
    assert state.brief_already_sent("2026-10-05", "222") is False
    data = state.load_sent()
    assert "brief:111:2026-10-05" in data
    assert data["brief:111:2026-10-05"]["quiet"] is True


def test_channel_key(tmp_path, monkeypatch):
    path = tmp_path / "sent.json"
    monkeypatch.setattr(state.config, "SENT_PATH", path)
    assert state.channel_already_sent("2026-10-05") is False
    state.mark_channel_sent("2026-10-05", ["x"])
    assert state.channel_already_sent("2026-10-05") is True
    assert "channel:2026-10-05" in state.load_sent()


def test_alert_already_ran_from_brief_or_channel(tmp_path, monkeypatch):
    path = tmp_path / "sent.json"
    monkeypatch.setattr(state.config, "SENT_PATH", path)
    assert state.alert_already_ran("2026-10-05") is False
    state.mark_brief_sent("2026-10-05", "111")
    assert state.alert_already_ran("2026-10-05") is True
    assert state.alert_already_ran("2026-10-06") is False


def test_latest_ipos_for_date(tmp_path, monkeypatch):
    snaps = tmp_path / "snapshots.json"
    monkeypatch.setattr(state.config, "SNAPSHOTS_PATH", snaps)
    state.save_snapshots(
        [
            {"ipo_id": "a", "date": "2026-10-05", "ts": "t1", "name": "A"},
            {"ipo_id": "a", "date": "2026-10-05", "ts": "t2", "name": "A2"},
            {"ipo_id": "b", "date": "2026-10-04", "ts": "t9", "name": "B"},
        ]
    )
    rows = state.latest_ipos_for_date("2026-10-05")
    assert len(rows) == 1
    assert rows[0]["name"] == "A2"
