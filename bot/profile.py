"""Apply and verify Telegram bot profile from shared/copy.json."""

from __future__ import annotations

import sys
from typing import Any

import requests

from bot import copy


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


_configure_stdio()


def _api(token: str) -> str:
    return f"https://api.telegram.org/bot{token}"


def _safe_print(*args: Any) -> None:
    text = " ".join(str(a) for a in args)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="replace").decode("ascii", errors="replace"))


def _call(api: str, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{api}/{method}"
    if payload is None:
        data = requests.get(url, timeout=30).json()
    else:
        data = requests.post(url, json=payload, timeout=30).json()
    _safe_print(method, "ok" if data.get("ok") else data)
    if not data.get("ok"):
        raise RuntimeError(f"{method} failed: {data}")
    return data["result"]


def apply_profile(token: str) -> None:
    """setMy* from copy.json. Idempotent when values are unchanged."""
    api = _api(token)
    commands = copy.load()["commands"]
    _call(
        api,
        "setMyCommands",
        {"commands": [{"command": k, "description": v} for k, v in commands.items()]},
    )
    _call(api, "setMyShortDescription", {"short_description": copy.t("bot.short_description")[:120]})
    _call(api, "setMyDescription", {"description": copy.t("bot.description")[:512]})
    _call(api, "setMyName", {"name": copy.t("bot.name")[:64]})


def verify_profile(token: str) -> None:
    """getMy* and compare to copy.json. Raises on mismatch."""
    api = _api(token)
    want_name = copy.t("bot.name")[:64]
    want_short = copy.t("bot.short_description")[:120]
    want_desc = copy.t("bot.description")[:512]
    want_cmds = {k: v for k, v in copy.load()["commands"].items()}

    got_name = (_call(api, "getMyName") or {}).get("name") or ""
    got_short = (_call(api, "getMyShortDescription") or {}).get("short_description") or ""
    got_desc = (_call(api, "getMyDescription") or {}).get("description") or ""
    got_cmds = {
        c["command"]: c["description"]
        for c in (_call(api, "getMyCommands") or [])
        if isinstance(c, dict) and "command" in c
    }

    errors: list[str] = []
    if got_name != want_name:
        errors.append(f"name: got {got_name!r} want {want_name!r}")
    if got_short != want_short:
        errors.append(f"short_description: got {got_short!r} want {want_short!r}")
    if got_desc != want_desc:
        errors.append(f"description mismatch ({len(got_desc)} vs {len(want_desc)} chars)")
    if got_cmds != want_cmds:
        errors.append(f"commands: got {got_cmds!r} want {want_cmds!r}")
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        raise RuntimeError("bot profile verification failed")
    _safe_print("profile ok")


def setup_and_verify(token: str) -> int:
    try:
        apply_profile(token)
        verify_profile(token)
    except Exception as exc:  # noqa: BLE001
        print(exc, file=sys.stderr)
        return 1
    return 0
