"""Fixed alert schedule (Mon-Fri 09:00-20:00 Asia/Singapore)."""
from __future__ import annotations

from datetime import datetime, timedelta

from settings import ALERT_DAYS, ALERT_END, ALERT_START, TIMEZONE


def is_active(now: datetime) -> bool:
    local = now.astimezone(TIMEZONE)
    if local.weekday() not in ALERT_DAYS:
        return False
    return ALERT_START <= local.time() < ALERT_END


def seconds_until_next_window(now: datetime) -> float:
    if is_active(now):
        return 0.0
    local = now.astimezone(TIMEZONE)
    for offset in range(8):
        day = local.date() + timedelta(days=offset)
        if day.weekday() not in ALERT_DAYS:
            continue
        start = datetime.combine(day, ALERT_START, tzinfo=TIMEZONE)
        if start > local:
            return (start - local).total_seconds()
    raise RuntimeError("ALERT_DAYS is empty")
