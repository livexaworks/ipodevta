"""Talk to the Cloudflare Worker: read user filters, publish the latest market cards."""

from __future__ import annotations

import logging
from typing import Any

import requests

from bot import config

log = logging.getLogger(__name__)


class WorkerError(RuntimeError):
    pass


def _endpoint(path: str) -> tuple[str, dict[str, str]]:
    base, secret = config.worker_base_url(), config.worker_secret()
    if not base or not secret:
        raise WorkerError("WEBHOOK_BASE_URL and EXPORT_SECRET must be set")
    return f"{base}{path}", {"Authorization": f"Bearer {secret}"}


def fetch_users() -> dict[str, dict[str, Any]]:
    """chat_id -> prefs for every user who has opened the bot."""
    url, headers = _endpoint("/export/users")
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise WorkerError(f"user export failed: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkerError("user export must be a JSON object")
    return data


def push_market(payload: dict[str, Any]) -> None:
    """Store the latest cards in KV so the Worker's Check now replies instantly."""
    url, headers = _endpoint("/market")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise WorkerError(f"market push failed: {exc}") from exc
