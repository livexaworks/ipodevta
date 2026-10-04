"""shared/copy.json is the single source for user-facing strings."""

from __future__ import annotations

import json
import re
from pathlib import Path

from bot import copy

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "workers" / "telegram" / "worker.js"
COPY_JS = ROOT / "workers" / "telegram" / "copy.js"


def test_copy_loads_and_templates():
    assert copy.t("buttons.preview") == "Preview GMP"
    assert copy.t("reasons.GMP_BELOW", actual=22, required=48) == "GMP 22%, needs 48%"
    assert copy.t("footer.data", hhmm="10:55").startswith("Data 10:55 IST")


def test_worker_copy_js_matches_shared():
    """Regenerate with: python workers/telegram/sync_copy.py"""
    shared = json.loads((ROOT / "shared" / "copy.json").read_text(encoding="utf-8"))
    text = COPY_JS.read_text(encoding="utf-8")
    assert text.startswith("// AUTO-GENERATED")
    # Extract the exported object
    start = text.index("export default ") + len("export default ")
    payload = text[start:].strip()
    if payload.endswith(";"):
        payload = payload[:-1]
    inline = json.loads(payload)
    assert inline == shared


def test_worker_js_has_no_user_facing_string_literals():
    """Worker must pull Telegram copy from COPY / t() / btn(), not hardcode it."""
    src = WORKER.read_text(encoding="utf-8")
    # Strip block comments and line comments roughly
    stripped = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    stripped = re.sub(r"//.*?$", "", stripped, flags=re.M)

    banned = [
        "Preview GMP",
        "Your filters",
        "On closing days",
        "Grey-market premium",
        "Saved preview",
        "Fetching fresh",
        "Mainboard only",
        "Join channel",
        "What you get",
        "Daily Brief",
        "Quick actions",
        "Feedback cancelled",
        "not investment advice",
        "Closing today ·",
    ]
    for phrase in banned:
        assert phrase not in stripped, f"user-facing literal still in worker.js: {phrase!r}"

    assert 'import COPY from "./copy.js"' in src
    assert 'githubDispatch(env, "alert"' in src or 'eventType' in src
    assert "async scheduled" in src
