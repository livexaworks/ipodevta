"""shared/copy.json is the single source for user-facing strings."""

from __future__ import annotations

import json
import re
from pathlib import Path

from bot import copy

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "workers" / "telegram" / "worker.js"
COPY_JS = ROOT / "workers" / "telegram" / "copy.js"


def test_templates_fill():
    assert copy.t("card.price", price="₹220") == "💰 Price ₹220"
    assert copy.t("card.sub", sub="2x", when="live 2:30 PM") == "📊 Subscription 2x (live 2:30 PM)"


def test_worker_copy_js_matches_shared():
    """Regenerate with: python workers/telegram/sync_copy.py"""
    shared = json.loads((ROOT / "shared" / "copy.json").read_text(encoding="utf-8"))
    text = COPY_JS.read_text(encoding="utf-8")
    payload = text[text.index("export default ") + len("export default "):].strip().rstrip(";")
    assert json.loads(payload) == shared


def test_worker_has_no_hardcoded_user_copy():
    src = re.sub(r"/\*.*?\*/|//.*?$", "", WORKER.read_text(encoding="utf-8"), flags=re.S | re.M)
    for phrase in ("Check now", "Your filters", "No IPO passed", "Today's IPOs", "not investment advice"):
        assert phrase not in src, f"user-facing literal in worker.js: {phrase!r}"


def test_worker_and_python_defaults_match():
    from bot import config

    src = WORKER.read_text(encoding="utf-8")
    m = re.search(r"const DEFAULTS = \{ board: \"(\w+)\", min_gmp_main: (\d+), min_gmp_sme: (\d+), min_total_sub: (\d+) \}", src)
    assert m, "DEFAULTS line changed shape"
    assert m.group(1) == config.DEFAULT_BOARD
    assert float(m.group(2)) == config.MIN_GMP_MAIN
    assert float(m.group(3)) == config.MIN_GMP_SME
    assert float(m.group(4)) == config.MIN_TOTAL_SUB


def test_worker_crons_match_wrangler():
    toml = (ROOT / "workers" / "telegram" / "wrangler.toml").read_text(encoding="utf-8")
    src = WORKER.read_text(encoding="utf-8")
    for cron in ("0 4 * * 1-5", "0 9 * * 1-5"):
        assert f'"{cron}"' in toml and f'"{cron}"' in src
