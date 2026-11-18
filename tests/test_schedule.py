from datetime import datetime, timezone

from schedule import is_active, seconds_until_next_window
from settings import TIMEZONE


def sgt(y, m, d, hh, mm):  # 2026-11-20 is a Friday
    return datetime(y, m, d, hh, mm, tzinfo=TIMEZONE).astimezone(timezone.utc)


def test_active_boundaries():
    assert is_active(sgt(2026, 11, 20, 19, 59))
    assert not is_active(sgt(2026, 11, 20, 20, 0))
    assert not is_active(sgt(2026, 11, 21, 12, 0))  # Saturday
    assert is_active(sgt(2026, 11, 23, 9, 0))  # Monday
    assert not is_active(sgt(2026, 11, 23, 8, 59))


def test_next_window_from_friday_evening():
    assert seconds_until_next_window(sgt(2026, 11, 20, 20, 0)) == 61 * 3600


def test_next_window_same_morning():
    assert seconds_until_next_window(sgt(2026, 11, 23, 8, 30)) == 30 * 60


def test_next_window_when_active_is_zero():
    assert seconds_until_next_window(sgt(2026, 11, 23, 10, 0)) == 0.0
