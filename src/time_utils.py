from __future__ import annotations

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
        return start <= current <= end
    return current >= start or current <= end
