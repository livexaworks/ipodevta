import json

from bot import config, state
from tests.conftest import TODAY


def test_sent_log_round_trip_and_no_raw_chat_ids():
    log = state.SentLog(TODAY)
    log.set_header(55)
    log.mark_channel("a-ipo", 56)
    log.mark_dm(987654321, "a-ipo")
    log.mark_done("channel")

    again = state.SentLog(TODAY)
    assert again.header_id == 55
    assert again.channel_sent("a-ipo")
    assert again.dm_sent(987654321) == ["a-ipo"]
    assert again.done("channel") and not again.done("bot")
    assert "987654321" not in config.SENT_PATH.read_text(encoding="utf-8")


def test_chat_hash_depends_on_secret(monkeypatch):
    a = state.chat_hash(42)
    monkeypatch.setenv("EXPORT_SECRET", "other")
    assert state.chat_hash(42) != a


def test_prunes_old_and_legacy_entries():
    config.SENT_PATH.write_text(json.dumps({
        "2026-09-01": {"channel": {}, "bot": {}},
        "2026-10-07": {"channel": {"ipo_ids": []}, "users": {"123456789": {}}},
        "brief:1:2026-10-07": {"ts": "x"},
        "2026-10-06": {"channel": {"header": 1, "ipos": {}, "done": "x"}, "bot": {"users": {}, "done": "x"}},
    }), encoding="utf-8")
    log = state.SentLog(TODAY)
    log.save()
    assert set(json.loads(config.SENT_PATH.read_text(encoding="utf-8"))) == {"2026-10-06", TODAY}


def test_dry_run_log_never_writes():
    log = state.SentLog(TODAY, persist=False)
    log.set_header(1)
    assert not config.SENT_PATH.exists()
