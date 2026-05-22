from __future__ import annotations

import math
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def now_in_timezone(timezone_name: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Singapore":
            return datetime.now(timezone(timedelta(hours=8)))
        raise


def parse_hhmm(value: str) -> time:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError(f"Invalid HH:MM time value: {value}") from exc
    return parsed.time()


def is_within_active_window(now: datetime, active_start: str, active_end: str) -> bool:
    start = parse_hhmm(active_start)
    end = parse_hhmm(active_end)
    current = now.timetz().replace(tzinfo=None)

    if start <= end:
        return start <= current < end
    return current >= start or current < end


def next_active_start_datetime(now: datetime, active_start: str, active_end: str) -> datetime:
    start = parse_hhmm(active_start)
    end = parse_hhmm(active_end)
    current = now.timetz().replace(tzinfo=None)

    today_start = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)

    if start <= end:
        if current < start:
            return today_start
        return today_start + timedelta(days=1)

    # Overnight window (example: 22:00 to 06:00).
    if end <= current < start:
        return today_start
    if current >= start:
        return today_start + timedelta(days=1)
    return today_start


def seconds_until_next_active_start(now: datetime, active_start: str, active_end: str) -> int:
    next_start = next_active_start_datetime(now, active_start, active_end)
    delta_seconds = (next_start - now).total_seconds()
    return max(1, math.ceil(delta_seconds))
