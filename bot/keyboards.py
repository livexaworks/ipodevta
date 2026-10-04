"""Telegram reply + inline keyboards for a button-first UX."""

from __future__ import annotations

from typing import Any

from bot import config, copy
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


def btn(key: str) -> str:
    return copy.t(f"buttons.{key}")


def main_reply_keyboard() -> dict[str, Any]:
    """Persistent bottom keyboard - no typing required."""
    return {
        "keyboard": [
            [{"text": btn("preview")}, {"text": btn("settings")}],
            [{"text": btn("help")}, {"text": btn("channel")}],
            [{"text": btn("feedback")}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def home_inline() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": btn("preview"), "callback_data": "preview"},
                {"text": btn("settings"), "callback_data": "settings"},
            ],
            [
                {"text": btn("help"), "callback_data": "help"},
                {"text": btn("join_channel"), "url": channel_url()},
            ],
            [{"text": btn("feedback"), "callback_data": "feedback"}],
        ]
    }


def brief_inline() -> dict[str, Any]:
    """One row: Filters (settings callback) + All IPOs (channel URL)."""
    return {
        "inline_keyboard": [
            [
                {"text": btn("filters"), "callback_data": "settings"},
                {"text": btn("all_ipos"), "url": "https://t.me/ipodevta"},
            ]
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
        label = copy.t("buttons.type_pct_prefixed", prefix=prefix.strip())
    else:
        label = btn("type_pct")
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
                "text": _mark(
                    nearly(sub, value),
                    copy.t("buttons.sub_preset", value=f"{value:g}"),
                ),
                "callback_data": f"sub:{value:g}",
            }
            for value in SUB_PRESETS
        ]
    )
    rows.append(
        [
            {
                "text": _mark(mode == BOARD_MAIN, btn("board_main")),
                "callback_data": "board:main",
            },
            {
                "text": _mark(mode == BOARD_SME, btn("board_sme")),
                "callback_data": "board:sme",
            },
            {
                "text": _mark(mode == BOARD_BOTH, btn("board_both")),
                "callback_data": "board:both",
            },
        ]
    )
    rows.append(
        [
            {"text": btn("preview"), "callback_data": "preview"},
            {"text": btn("home"), "callback_data": "home"},
        ]
    )
    return {"inline_keyboard": rows}
