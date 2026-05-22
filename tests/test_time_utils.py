from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.time_utils import (
    is_within_active_window,
    next_active_start_datetime,
    seconds_until_next_active_start,
)


SGT = timezone(timedelta(hours=8))


class TimeWindowTests(unittest.TestCase):
    def test_within_window_start_inclusive_end_exclusive(self) -> None:
        self.assertTrue(
            is_within_active_window(
                datetime(2026, 5, 22, 9, 0, 0, tzinfo=SGT), "09:00", "19:00"
            )
        )
        self.assertTrue(
            is_within_active_window(
                datetime(2026, 5, 22, 18, 59, 59, tzinfo=SGT), "09:00", "19:00"
            )
        )
        self.assertFalse(
            is_within_active_window(
                datetime(2026, 5, 22, 19, 0, 0, tzinfo=SGT), "09:00", "19:00"
            )
        )

    def test_next_start_before_window(self) -> None:
        now = datetime(2026, 5, 22, 8, 30, 0, tzinfo=SGT)
        next_start = next_active_start_datetime(now, "09:00", "19:00")
        self.assertEqual(datetime(2026, 5, 22, 9, 0, 0, tzinfo=SGT), next_start)
        self.assertEqual(1800, seconds_until_next_active_start(now, "09:00", "19:00"))

    def test_next_start_after_window(self) -> None:
        now = datetime(2026, 5, 22, 21, 0, 0, tzinfo=SGT)
        next_start = next_active_start_datetime(now, "09:00", "19:00")
        self.assertEqual(datetime(2026, 5, 23, 9, 0, 0, tzinfo=SGT), next_start)
        self.assertEqual(43200, seconds_until_next_active_start(now, "09:00", "19:00"))


if __name__ == "__main__":
    unittest.main()
