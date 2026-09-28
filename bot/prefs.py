"""User filter shape: separate mainboard and SME GMP bars."""

from __future__ import annotations

from typing import Any

from bot import config

MAIN_GMP_PRESETS = (24.0, 30.0, 34.0, 40.0, 50.0)
SME_GMP_PRESETS = (40.0, 45.0, 48.0, 55.0, 60.0)
SUB_PRESETS = (1.0, 2.0, 5.0)

BOARD_MAIN = "main"
BOARD_SME = "sme"
BOARD_BOTH = "both"


def board_mode(prefs: dict[str, Any] | None) -> str:
    """main, sme, or both. Legacy include_sme maps to both."""
    p = prefs or {}
    raw = str(p.get("board") or "").strip().lower()
    if raw in (BOARD_MAIN, BOARD_SME, BOARD_BOTH):
        return raw
    if p.get("include_sme"):
        return BOARD_BOTH
    return BOARD_MAIN


def gmp_main(prefs: dict[str, Any] | None) -> float:
    p = prefs or {}
    if p.get("min_gmp_main") is not None:
        return float(p["min_gmp_main"])
    if p.get("min_gmp_pct") is not None:
        return float(p["min_gmp_pct"])
    return float(config.MIN_GMP_MAIN)


def gmp_sme(prefs: dict[str, Any] | None) -> float:
    """SME bar. A legacy single GMP applies only when no SME field was saved."""
    p = prefs or {}
    if p.get("min_gmp_sme") is not None:
        return float(p["min_gmp_sme"])
    legacy = "min_gmp_sme" not in p and "board" not in p and p.get("min_gmp_pct") is not None
    if legacy:
        return float(p["min_gmp_pct"])
    return float(config.MIN_GMP_SME)


def gmp_for_board(prefs: dict[str, Any] | None, board: str | None) -> float:
    if (board or "").upper() == "SME":
        return gmp_sme(prefs)
    return gmp_main(prefs)


def board_fields(mode: str) -> dict[str, Any]:
    mode = mode if mode in (BOARD_MAIN, BOARD_SME, BOARD_BOTH) else BOARD_MAIN
    return {
        "board": mode,
        "include_sme": mode != BOARD_MAIN,
        "awaiting_input": None,
    }


def gmp_fields(which: str, value: float) -> dict[str, Any]:
    value = float(value)
    if which == BOARD_SME:
        return {"min_gmp_sme": value, "awaiting_input": None}
    return {"min_gmp_main": value, "min_gmp_pct": value, "awaiting_input": None}


def parse_pct(raw: str) -> float | None:
    text = (raw or "").strip().rstrip("%").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if value < 0 or value > 300:
        return None
    return value


def fingerprint(prefs: dict[str, Any] | None) -> dict[str, Any]:
    p = prefs or {}
    return {
        "board": board_mode(p),
        "min_gmp_main": gmp_main(p),
        "min_gmp_sme": gmp_sme(p),
        "min_total_sub": float(p.get("min_total_sub", config.MIN_TOTAL_SUB)),
    }


def nearly(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < 0.05
