"""Fallback alert must not call IPO Guru when sent.json already recorded today."""

from bot import run as run_mod
from bot import state


def test_alert_skip_collect_when_already_ran(tmp_path, monkeypatch):
    monkeypatch.setattr(state.config, "SENT_PATH", tmp_path / "sent.json")
    monkeypatch.setattr(state.config, "SNAPSHOTS_PATH", tmp_path / "snapshots.json")
    monkeypatch.setattr(state.config, "USERS_PATH", tmp_path / "users.json")
    state.mark_brief_sent("2026-10-05", "111", ipo_ids=["x"])
    monkeypatch.setattr(run_mod.config, "today_ist", lambda: "2026-10-05")

    def boom(**_kwargs):
        raise AssertionError("collect must not run on fallback")

    monkeypatch.setattr(run_mod, "collect", boom)
    monkeypatch.setattr(run_mod.users, "drain_updates", lambda **_k: 0)
    monkeypatch.setattr(run_mod.notify, "admin", lambda *a, **k: None)

    rc = run_mod.run("alert")
    assert rc == 0
