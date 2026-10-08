import pytest

from bot import collect
from bot.sources import bse, ipoguru
from tests.conftest import TODAY


def test_closed_ipos_dropped_and_bse_failure_tolerated(market, monkeypatch):
    monkeypatch.setattr(ipoguru, "fetch_open_ipos", lambda: [dict(i) for i in market])

    def broken():
        raise bse.BseError("403")

    monkeypatch.setattr(bse, "load_live_ipos", broken)
    out = collect.collect(TODAY)
    ids = [i["ipo_id"] for i in out.ipos]
    assert "rkfashion-accessories-sme-ipo" not in ids  # closed yesterday
    assert ids[0] == "vishal-nirmiti-ipo"  # closes today, listed first
    assert any("BSE subscription unavailable" in w for w in out.warnings)


def test_guru_failure_aborts(monkeypatch):
    def broken():
        raise ipoguru.IpoGuruError("401")

    monkeypatch.setattr(ipoguru, "fetch_open_ipos", broken)
    with pytest.raises(collect.CollectError):
        collect.collect(TODAY)
