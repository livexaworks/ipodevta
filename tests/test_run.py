from datetime import datetime

import pytest

from bot import config, run, state, telegram, worker_api
from bot.collect import is_open_on, order
from tests.conftest import FIXTURES, TODAY

FIXTURE = str(FIXTURES / "market.json")


@pytest.fixture
def open_ipos(market):
    return order([i for i in market if is_open_on(i, TODAY)])


def test_channel_posts_header_then_one_card_per_ipo(open_ipos):
    sender = run.DryRunSender()
    report = run.run_channel(
        open_ipos, today=TODAY, as_of="09:30", sent=state.SentLog(TODAY), sender=sender, channel="@ipodevta"
    )
    texts = [m["text"] for m in sender.sent]
    assert len(texts) == 1 + len(open_ipos) == report.posted
    assert texts[0].startswith("📊 <b>IPO Market")
    assert texts[1].startswith("<b>Vishal Nirmiti</b>")  # closing today leads
    assert all(m["reply_markup"] is None for m in sender.sent)  # channel cards carry no buttons
    assert all(t.count("<b>") == 1 for t in texts[1:])  # one IPO per message


def test_channel_rerun_sends_nothing_twice(open_ipos):
    log = state.SentLog(TODAY)
    run.run_channel(open_ipos, today=TODAY, as_of="09:30", sent=log, sender=run.DryRunSender(), channel="@c")
    again = run.DryRunSender()
    run.run_channel(open_ipos, today=TODAY, as_of="09:30", sent=state.SentLog(TODAY), sender=again, channel="@c")
    assert again.sent == []


def test_bot_sends_only_passing_cards_each_with_buttons(open_ipos):
    log = state.SentLog(TODAY)
    log.set_header(77)
    users = {"111": {"board": "both", "min_gmp_main": 30, "min_gmp_sme": 40, "min_total_sub": 1}}
    sender = run.DryRunSender()
    report = run.run_bot(open_ipos, users, today=TODAY, as_of="14:31", sent=log, sender=sender)

    assert [m["text"].splitlines()[0] for m in sender.sent] == ["<b>Vishal Nirmiti</b>"]
    assert report.posted == 1 and report.no_match == 0
    for m in sender.sent:
        row = m["reply_markup"]["inline_keyboard"][0]
        assert row[0]["url"] == "https://t.me/ipodevta/77"
        assert row[1]["callback_data"] == "settings"
    assert "passed your filters" not in "".join(m["text"] for m in sender.sent)


def test_only_first_card_makes_a_sound(open_ipos):
    lenient = {"board": "both", "min_gmp_main": 0, "min_gmp_sme": 0, "min_total_sub": 0}
    sender = run.DryRunSender()
    run.run_bot(open_ipos, {"1": lenient}, today=TODAY, as_of="14:31", sent=state.SentLog(TODAY), sender=sender)
    assert len(sender.sent) == 2
    assert [m["silent"] for m in sender.sent] == [False, True]


def test_no_match_message_once(open_ipos):
    strict = {"board": "main", "min_gmp_main": 99}
    log = state.SentLog(TODAY)
    sender = run.DryRunSender()
    report = run.run_bot(open_ipos, {"5": strict}, today=TODAY, as_of="14:31", sent=log, sender=sender)
    assert report.no_match == 1
    assert sender.sent[0]["text"].startswith("🚫 No IPO passed your filters today")
    assert sender.sent[0]["reply_markup"]["inline_keyboard"][0][1]["text"] == "⚙️ Filters"

    again = run.DryRunSender()
    run.run_bot(open_ipos, {"5": strict}, today=TODAY, as_of="14:31", sent=state.SentLog(TODAY), sender=again)
    assert again.sent == []


def test_empty_market_sends_nothing_anywhere():
    log = state.SentLog(TODAY)
    channel = run.DryRunSender()
    assert run.run_channel([], today=TODAY, as_of="09:30", sent=log, sender=channel, channel="@c").posted == 0
    strict = {"board": "main", "min_gmp_main": 99}
    dm = run.DryRunSender()
    report = run.run_bot([], {"1": {}, "2": strict}, today=TODAY, as_of="14:31", sent=log, sender=dm)
    assert channel.sent == [] and dm.sent == []
    assert report.no_match == 0
    assert report.line().startswith("IPODevta bot: no open IPOs, nothing sent")


def test_empty_market_run_completes(monkeypatch, tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(worker_api, "fetch_users", lambda: {"1": {}})
    monkeypatch.setattr(telegram, "send", lambda *a, **k: pytest.fail("nothing to send on an empty day"))
    assert run.run("bot", fixture=str(empty)) == 0
    assert run.run("channel", fixture=str(empty), force=True) == 0
    assert state.SentLog(TODAY).done("bot")


def test_blocked_user_does_not_fail_the_run(open_ipos):
    class Blocking(run.DryRunSender):
        def send(self, chat_id, html, **kw):
            raise telegram.ChatUnavailable("blocked")

    report = run.run_bot(open_ipos, {"9": {}}, today=TODAY, as_of="14:31", sent=state.SentLog(TODAY), sender=Blocking())
    assert report.blocked == 1 and report.failed == 0


def test_card_text_identical_across_channel_dm_and_worker_payload(open_ipos):
    channel = run.DryRunSender()
    run.run_channel(open_ipos, today=TODAY, as_of="09:30", sent=state.SentLog(TODAY), sender=channel, channel="@c")
    payload = run.market_payload(open_ipos, today=TODAY, as_of="09:30", phase="channel", header_id=1)
    assert [m["text"] for m in channel.sent[1:]] == [i["card"] for i in payload["ipos"]]

    dm = run.DryRunSender()
    lenient = {"board": "both", "min_gmp_main": 0, "min_gmp_sme": 0, "min_total_sub": 0}
    run.run_bot(open_ipos, {"1": lenient}, today=TODAY, as_of="14:31", sent=state.SentLog("2026-10-08"), sender=dm)
    bot_payload = run.market_payload(open_ipos, today=TODAY, as_of="14:31", phase="bot", header_id=1)
    cards_by_id = {i["ipo_id"]: i["card"] for i in bot_payload["ipos"]}
    assert all(m["text"] in cards_by_id.values() for m in dm.sent)


def test_run_bot_end_to_end_marks_done(monkeypatch, capsys):
    monkeypatch.setattr(worker_api, "fetch_users", lambda: {"1": {}, "2": {"board": "sme", "min_gmp_sme": 90}})
    assert run.run("bot", fixture=FIXTURE) == 0
    log = state.SentLog(TODAY)
    assert log.done("bot")
    assert log.dm_sent("1") == ["vishal-nirmiti-ipo"]
    assert log.dm_sent("2") == [state.NO_MATCH]
    # second run is a no-op
    assert run.run("bot", fixture=FIXTURE) == 0


def test_dry_run_prints_and_writes_no_state(capsys):
    assert run.run("channel", dry_run=True, force=True, fixture=FIXTURE) == 0
    assert "<b>Vishal Nirmiti</b>" in capsys.readouterr().out
    assert not config.SENT_PATH.exists()


def test_deadline_skips(monkeypatch):
    monkeypatch.setattr(config, "now_ist", lambda: datetime.fromisoformat(f"{TODAY}T13:05:00+05:30"))
    sent = []
    monkeypatch.setattr(telegram, "send", lambda *a, **k: sent.append(a) or {"message_id": 1})
    assert run.run("channel", fixture=FIXTURE) == 0
    assert sent == []


def test_holiday_skips(monkeypatch):
    monkeypatch.setattr(config, "now_ist", lambda: datetime.fromisoformat("2026-10-20T09:30:00+05:30"))
    monkeypatch.setattr(telegram, "send", lambda *a, **k: pytest.fail("must not send on a holiday"))
    assert run.run("channel", fixture=FIXTURE) == 0


def test_admin_warned_when_holiday_year_missing(monkeypatch):
    monkeypatch.setattr(config, "now_ist", lambda: datetime.fromisoformat("2027-01-04T09:30:00+05:30"))
    alerts = []
    monkeypatch.setattr(telegram, "admin", alerts.append)
    assert run.run("channel", fixture=FIXTURE) == 0
    assert "no 2027 NSE holidays" in alerts[-1]


@pytest.fixture(autouse=True)
def live_sender_is_dry(monkeypatch):
    """Non-dry run() calls use LiveSender; route it to a fake so nothing leaves the machine."""
    counter = {"n": 0}

    def fake_send(chat_id, html, **kw):
        counter["n"] += 1
        return {"message_id": counter["n"]}

    monkeypatch.setattr(telegram, "send", fake_send)
    monkeypatch.setattr(telegram, "admin", lambda text: None)
