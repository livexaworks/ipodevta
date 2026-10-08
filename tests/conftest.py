"""Shared fixtures: isolate data/ writes and pin 'today'."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from bot import config

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TODAY = "2026-10-08"  # Thursday, a market day


@pytest.fixture
def market() -> list[dict]:
    return json.loads((FIXTURES / "market.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SENT_PATH", tmp_path / "sent.json")
    monkeypatch.setattr(config, "today_ist", lambda: TODAY)
    monkeypatch.setattr(config, "now_ist", lambda: datetime.fromisoformat(f"{TODAY}T14:31:00+05:30"))
    # Empty values block .env from leaking real tokens into tests.
    for name in ("TELEGRAM_TOKEN", "CHANNEL_URL", "WEBHOOK_BASE_URL", "ADMIN_CHAT_ID", "IPOGURU_API_KEY"):
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("CHANNEL_ID", "@ipodevta")
    monkeypatch.setenv("EXPORT_SECRET", "test-secret")
    return tmp_path
