"""User prefs helpers."""

from bot import state


def test_default_prefs(tmp_path, monkeypatch):
    monkeypatch.setattr(state.config, "USERS_PATH", tmp_path / "users.json")
    prefs = state.get_or_create_user(12345)
    assert prefs["min_gmp_pct"] == 24.0
    assert prefs["include_sme"] is False
    updated = state.update_user(12345, min_gmp_pct=30.0, include_sme=True)
    assert updated["min_gmp_pct"] == 30.0
    assert updated["include_sme"] is True
    again = state.load_users()["12345"]
    assert again["min_gmp_pct"] == 30.0
