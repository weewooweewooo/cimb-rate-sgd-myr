import asyncio
import logging
from datetime import datetime, timezone

from db import Database
from models import RateState
from monitor import FetchHealth, Fetchers, evaluate_users, poll_once
from providers import ProviderError

NOW = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)  # Wed 11:00 SGT


def const(value):
    async def fetch():
        return value
    return fetch


def failing(msg="boom"):
    async def fetch(*_):
        raise ProviderError(msg)
    return fetch


class FakeSender:
    def __init__(self, ok=True):
        self.ok = ok
        self.sent = []

    async def send_alert(self, user, state):
        self.sent.append((user.discord_user_id, state.cimb_rate))
        return self.ok


def test_poll_updates_state_and_db():
    db, state = Database(":memory:"), RateState()
    asyncio.run(poll_once(Fetchers(cimb=const(3.17)), db, state, FetchHealth(), NOW))
    assert state.cimb_rate == 3.17 and state.cimb_at == NOW
    assert db.rates_since("cimb", NOW) == [(NOW, 3.17)]


def test_cimb_failure_clears_rate():
    db, state = Database(":memory:"), RateState(cimb_rate=3.17)
    asyncio.run(poll_once(Fetchers(cimb=failing()), db, state, FetchHealth(), NOW))
    assert state.cimb_rate is None


def test_failure_logged_once_then_recovery(caplog):
    caplog.set_level(logging.WARNING)
    h = FetchHealth()
    for _ in range(5):
        h.failed("cimb", "boom")
    h.ok("cimb")
    h.ok("cimb")
    assert [r.levelname for r in caplog.records] == ["ERROR", "WARNING"]


def _db_with_user(peak=0.0):
    db = Database(":memory:")
    db.create_user("1", "S", target_rate=3.16)
    db.update_user("1", peak_rate=peak)
    return db


def test_evaluate_sends_and_sets_peak():
    db, sender = _db_with_user(), FakeSender()
    asyncio.run(evaluate_users(db, sender, RateState(cimb_rate=3.17), NOW))
    assert sender.sent == [("1", 3.17)]
    user = db.get_user("1")
    assert user.peak_rate == 3.17 and user.last_alerted_at == NOW.isoformat()


def test_evaluate_failed_send_keeps_peak():
    db, sender = _db_with_user(), FakeSender(ok=False)
    asyncio.run(evaluate_users(db, sender, RateState(cimb_rate=3.17), NOW))
    assert db.get_user("1").peak_rate == 0.0


def test_evaluate_reset():
    db, sender = _db_with_user(peak=3.17), FakeSender()
    asyncio.run(evaluate_users(db, sender, RateState(cimb_rate=3.15), NOW))
    assert sender.sent == [] and db.get_user("1").peak_rate == 0.0


def test_evaluate_no_rates_does_nothing():
    db, sender = _db_with_user(), FakeSender()
    asyncio.run(evaluate_users(db, sender, RateState(), NOW))
    assert sender.sent == []


# ---- Wise (Phase 2) ------------------------------------------------------

from compare import quotes_for  # noqa: E402
from models import WiseFee  # noqa: E402


def fee_fetcher(fee, calls):
    async def fetch(amount):
        calls.append(amount)
        return fee
    return fetch


def test_both_providers_recorded():
    db, state, calls = Database(":memory:"), RateState(), []
    fetchers = Fetchers(cimb=const(3.17), wise_live=const(3.18), wise_fee=fee_fetcher(WiseFee(0.6, 0.003), calls))
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW))
    assert state.wise_rate == 3.18 and state.wise_at == NOW
    assert db.rates_since("wise", NOW) == [(NOW, 3.18)]
    assert state.wise_fee == WiseFee(0.6, 0.003) and db.latest_wise_fee() == WiseFee(0.6, 0.003)
    assert calls == [1000.0]


def test_wise_failure_keeps_cimb_only():
    db, state = Database(":memory:"), RateState(wise_rate=3.18)
    fetchers = Fetchers(cimb=const(3.17), wise_live=failing(), wise_fee=fee_fetcher(WiseFee(0.53, 0.0025), []))
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW))
    assert state.wise_rate is None
    assert [q.provider for q in quotes_for(state, 1000)] == ["cimb"]


def test_fee_checked_once_per_day():
    db, state, calls = Database(":memory:"), RateState(), []
    fetchers = Fetchers(cimb=const(3.17), wise_live=const(3.18), wise_fee=fee_fetcher(WiseFee(0.53, 0.0025), calls))
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW))
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW.replace(hour=8)))  # same SGT day (16:00)
    assert len(calls) == 1
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW.replace(day=19)))
    assert len(calls) == 2


def test_fee_check_failure_keeps_previous_fee():
    db, state = Database(":memory:"), RateState(wise_fee=WiseFee(0.7, 0.004))
    fetchers = Fetchers(cimb=const(3.17), wise_live=const(3.18), wise_fee=failing())
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW))
    assert state.wise_fee == WiseFee(0.7, 0.004)
    assert state.fee_checked_on is not None  # retry tomorrow, not every minute
