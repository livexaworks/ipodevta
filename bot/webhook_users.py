"""Pull registered user prefs from the Cloudflare Worker export endpoint."""

from __future__ import annotations

import logging
from typing import Any

import requests

from bot import config

log = logging.getLogger(__name__)


def webhook_enabled() -> bool:
    config.load_dotenv()
    return bool(config.webhook_export_url() and config.webhook_export_secret())


def fetch_users() -> dict[str, Any] | None:
    """Return users map from Worker, or None if webhook export is not configured."""
    url = config.webhook_export_url()
    secret = config.webhook_export_secret()
    if not url or not secret:
        return None
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {secret}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("export payload must be an object")
        return data
    except Exception as exc:  # noqa: BLE001
        log.error("webhook user export failed: %s", exc)
        return None
