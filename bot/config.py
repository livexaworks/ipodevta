"""Environment loading, constants, and IST time helpers."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SNAPSHOTS_PATH = DATA_DIR / "snapshots.json"
SENT_PATH = DATA_DIR / "sent.json"
HOLIDAYS_PATH = DATA_DIR / "holidays.json"

IST = timezone(timedelta(hours=5, minutes=30))

REPO_URL = "https://github.com/livexaworks/ipodevta"
USER_AGENT = f"IPODevtaBot/2.0 (+{REPO_URL})"

# BSE public bookbuilding APIs (category subscription only).
BSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com",
}
BSE_LIVE = (
    "https://api.bseindia.com/BseIndiaAPI/api/GetPublicIssue_par_updated/w"
    "?flag=1&status=L"
)
BSE_CATDEM = (
    "https://api.bseindia.com/BseIndiaAPI/api/"
    "Pubissues_GetBkbldgCatdem_PAR_ng/w?IPO_NO={ipo_no}"
)
BSE_CATDEM_NEW = (
    "https://api.bseindia.com/BseIndiaAPI/api/"
    "Pubissues_GetBkbldgCatdem_PAR_bbnew_ng/w?IPO_NO={ipo_no}"
)

# Default filters for users who have not customised (mirrors worker.js DEFAULTS).
DEFAULT_BOARD = "main"
MIN_GMP_MAIN = 34.0
MIN_GMP_SME = 48.0
MIN_TOTAL_SUB = 1.0

# Daily schedule (IST). Runs after the deadline skip and alert the admin.
CHANNEL_DEADLINE = "13:00"
BOT_DEADLINE = "16:30"

RETENTION_DAYS = 14


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env (utf-8-sig for PowerShell BOM)."""
    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env(name: str, default: str = "") -> str:
    load_dotenv()
    return os.environ.get(name, default).strip()


def telegram_token() -> str:
    return env("TELEGRAM_TOKEN")


def channel_id() -> str:
    return env("CHANNEL_ID", "@ipodevta")


def channel_url() -> str:
    """Public t.me link. Numeric channel ids need CHANNEL_URL to be set."""
    explicit = env("CHANNEL_URL")
    if explicit:
        return explicit.rstrip("/")
    cid = channel_id()
    if cid.startswith("@"):
        return f"https://t.me/{cid[1:]}"
    return "https://t.me/ipodevta"


def admin_chat_id() -> str:
    return env("ADMIN_CHAT_ID")


def worker_base_url() -> str:
    return env("WEBHOOK_BASE_URL").rstrip("/")


def worker_secret() -> str:
    return env("EXPORT_SECRET")


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> str:
    return now_ist().date().isoformat()


def format_ist(dt: datetime | None = None) -> str:
    d = dt or now_ist()
    d = d.replace(tzinfo=IST) if d.tzinfo is None else d.astimezone(IST)
    return d.isoformat(timespec="seconds")


def holidays() -> set[str]:
    if not HOLIDAYS_PATH.is_file():
        return set()
    data = json.loads(HOLIDAYS_PATH.read_text(encoding="utf-8"))
    return {str(d) for d in data.get("dates") or []}


def is_market_day(date_iso: str) -> bool:
    d = datetime.strptime(date_iso, "%Y-%m-%d")
    return d.weekday() < 5 and date_iso not in holidays()
