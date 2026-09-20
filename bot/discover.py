"""
ONE-OFF: dump raw BSE API responses so parsers can be written against real keys.

Run:  python -m bot.discover

Writes fixtures/bse_live.json and fixtures/bse_catdem_<id>.json,
prints structure + flattened key paths, then exits.
Do not invent BSE field names — paste this output back before writing bse.py parsers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import requests

from bot import config


def flatten_keys(obj: Any, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(obj, dict):
        if not obj:
            paths.append(prefix + "{}")
            return paths
        for key, val in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(flatten_keys(val, path))
    elif isinstance(obj, list):
        if not obj:
            paths.append(prefix + "[]")
            return paths
        paths.append(f"{prefix}[len={len(obj)}]")
        paths.extend(flatten_keys(obj[0], f"{prefix}[0]"))
    else:
        typ = type(obj).__name__
        sample = repr(obj)
        if len(sample) > 80:
            sample = sample[:77] + "..."
        paths.append(f"{prefix}: {typ} = {sample}")
    return paths


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {path}")


def fetch_json(url: str) -> Any:
    resp = requests.get(url, headers=config.BSE_HEADERS, timeout=30)
    print(f"GET {url}")
    print(f"  status={resp.status_code} content-type={resp.headers.get('Content-Type')}")
    resp.raise_for_status()
    return resp.json()


def extract_ipo_ids(payload: Any) -> list[str]:
    """Use IPO_NO from each live Table row (confirmed field from discover fixtures)."""
    ids: list[str] = []
    seen: set[str] = set()
    for row in _as_records(payload):
        val = row.get("IPO_NO")
        if val is None or val == "" or val == 1:
            # IPO_NO==1 appears on non-IPO placeholders in the live feed
            continue
        s = str(val).strip()
        if s and s not in seen:
            seen.add(s)
            ids.append(s)
    return ids


def _as_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("Table", "Table1", "data", "Data", "list", "List", "result", "Result"):
            val = payload.get(key)
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return val
        # single wrapper with one list value
        for val in payload.values():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return list(val)
    return []


def main() -> int:
    config.FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    print("=== BSE_LIVE ===")
    live = fetch_json(config.BSE_LIVE)
    live_path = config.FIXTURES_DIR / "bse_live.json"
    _write_json(live_path, live)

    print(f"Top-level type: {type(live).__name__}")
    if isinstance(live, dict):
        print(f"Top-level keys: {list(live.keys())}")
    records = _as_records(live)
    print(f"Record count (best-effort): {len(records)}")
    if records:
        print(f"First record keys: {list(records[0].keys())}")
        print("--- first record (pretty) ---")
        print(json.dumps(records[0], indent=2, ensure_ascii=False)[:4000])
    else:
        print("WARNING: could not locate a list of records in the live payload")
        print(json.dumps(live, indent=2, ensure_ascii=False)[:4000])

    print("\n=== Flattened key paths (live) ===")
    for line in flatten_keys(live):
        print(line)

    ids = extract_ipo_ids(live)
    print(f"\n=== Extracted IPO identifiers ({len(ids)}) ===")
    for i in ids:
        print(f"  {i}")

    if not ids:
        print(
            "\nNo IPO identifiers found. Fixtures still saved. "
            "Paste this output so parsers can be designed manually.",
            file=sys.stderr,
        )
        return 1

    for ipo_no in ids:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in ipo_no)
        for label, template in (
            ("catdem", config.BSE_CATDEM),
            ("catdem_new", config.BSE_CATDEM_NEW),
        ):
            url = template.format(ipo_no=ipo_no)
            print(f"\n=== {label} IPO_NO={ipo_no} ===")
            try:
                data = fetch_json(url)
            except Exception as exc:  # noqa: BLE001
                print(f"  FAILED: {exc}")
                continue
            out = config.FIXTURES_DIR / f"bse_{label}_{safe}.json"
            _write_json(out, data)
            print(f"Top-level type: {type(data).__name__}")
            if isinstance(data, dict):
                print(f"Top-level keys: {list(data.keys())}")
            print("--- flattened ---")
            for line in flatten_keys(data):
                print(line)

    print(
        "\nDone. Paste the printed output (and note any fixture files) "
        "so bse.py can be written against real field names."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
