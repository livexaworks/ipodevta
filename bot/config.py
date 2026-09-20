"""Environment loading, constants, and IST time helpers."""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
FIXTURES_DIR = ROOT / "fixtures"
SNAPSHOTS_PATH = DATA_DIR / "snapshots.json"
SENT_PATH = DATA_DIR / "sent.json"
USERS_PATH = DATA_DIR / "users.json"

IST = timezone(timedelta(hours=5, minutes=30))

REPO_URL = "https://github.com/weblrsolutions/ipodevta"
USER_AGENT = f"IPOGmpBot/1.0 (+{REPO_URL}) personal-use"

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
BSE_UPCOMING = (
    "https://api.bseindia.com/BseIndiaAPI/api/GetPublicIssue_par_updated/w"
    "?flag=1&status=F"
)
BSE_CATDEM = (
    "https://api.bseindia.com/BseIndiaAPI/api/"
    "Pubissues_GetBkbldgCatdem_PAR_ng/w?IPO_NO={ipo_no}"
)
BSE_CATDEM_NEW = (
    "https://api.bseindia.com/BseIndiaAPI/api/"
    "Pubissues_GetBkbldgCatdem_PAR_bbnew_ng/w?IPO_NO={ipo_no}"
)

GMP_URLS = {
    "investorgain": "https://www.investorgain.com/report/ipo-gmp-live/331/",
    "ipowatch": "https://ipowatch.in/ipo-grey-market-premium-latest-ipo-gmp/",
    "ipocentral": "https://ipocentral.in/ipo-discussion/",
}

# Default gates (used when a user has not customized)
MIN_GMP_PCT = 24.0
MIN_TOTAL_SUB = 1.0
MIN_CONFIDENCE = "medium"
INCLUDE_SME = False
BLOCK_FALLING_GMP = True

CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}

SNAPSHOT_RETENTION_DAYS = 120


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env (utf-8-sig for PowerShell BOM)."""
    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return
    text = env_path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def telegram_token() -> str:
    load_dotenv()
    return os.environ.get("TELEGRAM_TOKEN", "").strip()


def channel_id() -> str:
    load_dotenv()
    return os.environ.get("CHANNEL_ID", "@ipodevta").strip()


def admin_chat_id() -> str:
    load_dotenv()
    return os.environ.get("ADMIN_CHAT_ID", "").strip()


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> str:
    """Return today's date in IST as YYYY-MM-DD."""
    return now_ist().date().isoformat()


def format_ist(dt: datetime | None = None) -> str:
    d = dt or now_ist()
    if d.tzinfo is None:
        d = d.replace(tzinfo=IST)
    else:
        d = d.astimezone(IST)
    return d.isoformat(timespec="seconds")
