"""Load shared user-facing copy from shared/copy.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

COPY_PATH = Path(__file__).resolve().parent.parent / "shared" / "copy.json"


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    data = json.loads(COPY_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("shared/copy.json must be an object")
    return data


def get(path: str, default: Any = None) -> Any:
    """Dot-path lookup, e.g. get('buttons.check')."""
    cur: Any = load()
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def t(path: str, **kwargs: Any) -> str:
    """Fetch a string template and fill {placeholders}; unknown ones stay as-is."""
    raw = get(path)
    if raw is None:
        raise KeyError(f"copy path not found: {path}")
    text = str(raw)
    if not kwargs:
        return text

    class _Map(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return text.format_map(_Map(**{k: "" if v is None else v for k, v in kwargs.items()}))
