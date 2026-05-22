from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv
from os import getenv

PUSHOVER_ENDPOINT = "https://api.pushover.net/1/messages.json"


class NotificationError(RuntimeError):
    """Raised for invalid notification configuration."""


@dataclass(frozen=True)
class NotificationResult:
    success: bool
    dry_run: bool
    details: str


def send_pushover_alert(*, title: str, message: str, dry_run: bool) -> NotificationResult:
    load_dotenv()

    if dry_run:
        print(f"[DRY-RUN ALERT] {title} | {message}")
        return NotificationResult(success=True, dry_run=True, details="dry-run only")

    app_token = getenv("PUSHOVER_APP_TOKEN", "").strip()
    user_key = getenv("PUSHOVER_USER_KEY", "").strip()
    if not app_token or not user_key:
        raise NotificationError(
            "Missing PUSHOVER_APP_TOKEN or PUSHOVER_USER_KEY in .env for live alerts."
        )

    payload: dict[str, Any] = {
        "token": app_token,
        "user": user_key,
        "title": title,
        "message": message,
        "priority": 1,
    }

    try:
        response = requests.post(PUSHOVER_ENDPOINT, data=payload, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        return NotificationResult(success=False, dry_run=False, details=f"request failed: {exc}")

    return NotificationResult(
        success=True,
        dry_run=False,
        details=f"status={response.status_code}",
    )
