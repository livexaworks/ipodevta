"""Telegram reply + inline keyboards for a button-first UX."""

from __future__ import annotations

from typing import Any

from bot import config


def channel_url() -> str:
    cid = config.channel_id().strip()
    if cid.startswith("@"):
        return f"https://t.me/{cid[1:]}"
    if cid.startswith("-"):
        # numeric channel id — fall back to public username if set in env example
        return "https://t.me/ipodevta"
    return f"https://t.me/{cid}"


def main_reply_keyboard() -> dict[str, Any]:
    """Persistent bottom keyboard — no typing required."""
    return {
        "keyboard": [
            [{"text": "Preview GMP"}, {"text": "Settings"}],
            [{"text": "Help"}, {"text": "Channel"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def home_inline() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Preview GMP", "callback_data": "preview"},
                {"text": "Settings", "callback_data": "settings"},
            ],
            [
                {"text": "Help", "callback_data": "help"},
                {"text": "Join channel", "url": channel_url()},
            ],
        ]
    }


def settings_inline(prefs: dict[str, Any]) -> dict[str, Any]:
    gmp = float(prefs.get("min_gmp_pct", config.MIN_GMP_PCT))
    sub = float(prefs.get("min_total_sub", config.MIN_TOTAL_SUB))
    sme = bool(prefs.get("include_sme", config.INCLUDE_SME))

    def mark(active: bool, label: str) -> str:
        return f"✓ {label}" if active else label

    return {
        "inline_keyboard": [
            [
                {"text": mark(gmp == 20, "GMP 20%"), "callback_data": "gmp:20"},
                {"text": mark(gmp == 24, "GMP 24%"), "callback_data": "gmp:24"},
                {"text": mark(gmp == 30, "GMP 30%"), "callback_data": "gmp:30"},
            ],
            [
                {"text": mark(gmp == 40, "GMP 40%"), "callback_data": "gmp:40"},
                {"text": mark(gmp == 50, "GMP 50%"), "callback_data": "gmp:50"},
            ],
            [
                {"text": mark(sub == 1, "Sub 1x"), "callback_data": "sub:1"},
                {"text": mark(sub == 2, "Sub 2x"), "callback_data": "sub:2"},
                {"text": mark(sub == 5, "Sub 5x"), "callback_data": "sub:5"},
            ],
            [
                {
                    "text": mark(not sme, "MAIN only"),
                    "callback_data": "board:main",
                },
                {
                    "text": mark(sme, "MAIN + SME"),
                    "callback_data": "board:all",
                },
            ],
            [
                {"text": "Preview GMP", "callback_data": "preview"},
                {"text": "Home", "callback_data": "home"},
            ],
        ]
    }
