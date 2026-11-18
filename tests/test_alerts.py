from datetime import datetime, timedelta, timezone

from alerts import decide
from models import User

NOW = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)


def u(**kw):
    return User("1", "a", target_rate=3.16, enabled=True, **kw)


def test_first_alert_at_target():
    assert decide(u(), 3.16, NOW) == "alert"


def test_step_required():
    assert decide(u(peak_rate=3.1600), 3.1609, NOW) == "none"
    assert decide(u(peak_rate=3.1600), 3.1610, NOW) == "alert"


def test_reset_below_target():
    assert decide(u(peak_rate=3.17), 3.1599, NOW) == "reset"


def test_below_target_no_peak():
    assert decide(u(), 3.15, NOW) == "none"


def test_disabled():
    assert decide(u(enabled=False), 3.20, NOW) == "none"


def test_snoozed():
    later = (NOW + timedelta(minutes=30)).isoformat()
    assert decide(u(snoozed_until=later), 3.20, NOW) == "none"
    earlier = (NOW - timedelta(minutes=1)).isoformat()
    assert decide(u(snoozed_until=earlier), 3.20, NOW) == "alert"
