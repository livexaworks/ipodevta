"""Telegram reply + inline keyboards for a button-first UX."""

from __future__ import annotations

from typing import Any

from bot import config
from bot.prefs import (
    BOARD_BOTH,
    BOARD_MAIN,
    BOARD_SME,
    MAIN_GMP_PRESETS,
    SME_GMP_PRESETS,
    SUB_PRESETS,
    board_mode,
    gmp_main,
    gmp_sme,
    nearly,
)


def channel_url() -> str:
    cid = config.channel_id().strip()
    if cid.startswith("@"):
        return f"https://t.me/{cid[1:]}"
    if cid.startswith("-"):
        return "https://t.me/ipodevta"
    return f"https://t.me/{cid}"


def main_reply_keyboard() -> dict[str, Any]:
    """Persistent bottom keyboard - no typing required."""
    return {
        "keyboard": [
            [{"text": "Preview GMP"}, {"text": "Settings"}],
            [{"text": "Help"}, {"text": "Channel"}],
            [{"text": "Feedback"}],
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
            [{"text": "Feedback", "callback_data": "feedback"}],
        ]
    }


def _mark(active: bool, label: str) -> str:
    return f"✓ {label}" if active else label


def _pct_row(
    current: float, presets: tuple[float, ...], which: str, *, prefix: str = ""
) -> list[dict[str, str]]:
    row = []
    for value in presets:
        row.append(
            {
                "text": _mark(nearly(current, value), f"{prefix}{value:g}%"),
                "callback_data": f"gmp:{which}:{value:g}",
            }
        )
    return row


def _custom_button(
    current: float, presets: tuple[float, ...], which: str, *, prefix: str = ""
) -> dict[str, str]:
    custom = not any(nearly(current, value) for value in presets)
    if custom:
        label = f"{prefix}{current:g}%"
    elif prefix:
        label = f"Type {prefix.strip()}"
    else:
        label = "Type %"
    return {
        "text": _mark(custom, label),
        "callback_data": f"gmp:ask:{which}",
    }


def _chunk(buttons: list[dict[str, str]], size: int = 3) -> list[list[dict[str, str]]]:
    return [buttons[i : i + size] for i in range(0, len(buttons), size)]


def settings_inline(prefs: dict[str, Any]) -> dict[str, Any]:
    mode = board_mode(prefs)
    sub = float(prefs.get("min_total_sub", config.MIN_TOTAL_SUB))
    rows: list[list[dict[str, str]]] = []

    prefix_main = "M " if mode == BOARD_BOTH else ""
    prefix_sme = "S " if mode == BOARD_BOTH else ""

    if mode in (BOARD_MAIN, BOARD_BOTH):
        main_buttons = _pct_row(gmp_main(prefs), MAIN_GMP_PRESETS, "main", prefix=prefix_main)
        main_buttons.append(
            _custom_button(gmp_main(prefs), MAIN_GMP_PRESETS, "main", prefix=prefix_main)
        )
        rows.extend(_chunk(main_buttons))

    if mode in (BOARD_SME, BOARD_BOTH):
        sme_buttons = _pct_row(gmp_sme(prefs), SME_GMP_PRESETS, "sme", prefix=prefix_sme)
        sme_buttons.append(
            _custom_button(gmp_sme(prefs), SME_GMP_PRESETS, "sme", prefix=prefix_sme)
        )
        rows.extend(_chunk(sme_buttons))

    rows.append(
        [
            {
                "text": _mark(nearly(sub, value), f"Sub {value:g}x"),
                "callback_data": f"sub:{value:g}",
            }
            for value in SUB_PRESETS
        ]
    )
    rows.append(
        [
            {"text": _mark(mode == BOARD_MAIN, "Mainboard"), "callback_data": "board:main"},
            {"text": _mark(mode == BOARD_SME, "SME"), "callback_data": "board:sme"},
            {"text": _mark(mode == BOARD_BOTH, "Both"), "callback_data": "board:both"},
        ]
    )
    rows.append(
        [
            {"text": "Preview GMP", "callback_data": "preview"},
            {"text": "Home", "callback_data": "home"},
        ]
    )
    return {"inline_keyboard": rows}
