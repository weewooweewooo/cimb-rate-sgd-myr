"""Poll loop: fetch rates inside the schedule, store them, alert users."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Awaitable, Callable, Protocol

from alerts import decide
from compare import quotes_for
from db import Database
from models import RateState, User, WiseFee
from schedule import is_active, seconds_until_next_window
from settings import ALERT_REFERENCE_SGD, HISTORY_RETENTION_DAYS, RATE_POLL_SECONDS, TIMEZONE

log = logging.getLogger(__name__)

MAX_IDLE_SLEEP_SECONDS = 3600


class FetchHealth:
    """Log a provider failure once per outage, and once on recovery."""

    def __init__(self) -> None:
        self._failing: set[str] = set()

    def ok(self, name: str) -> None:
        if name in self._failing:
            self._failing.discard(name)
            log.warning("%s fetch recovered", name)

    def failed(self, name: str, detail: str) -> None:
        if name not in self._failing:
            self._failing.add(name)
            log.error("%s fetch failing: %s", name, detail)


@dataclass
class Fetchers:
    cimb: Callable[[], Awaitable[float]]
    wise_live: Callable[[], Awaitable[float]] | None = None
    wise_fee: Callable[[float], Awaitable[WiseFee]] | None = None


class AlertSender(Protocol):
    async def send_alert(self, user: User, state: RateState) -> bool: ...


async def poll_once(
    fetchers: Fetchers, db: Database, state: RateState, health: FetchHealth, now: datetime
) -> None:
    try:
        rate = await fetchers.cimb()
    except Exception as exc:  # one provider must never stop the loop
        health.failed("cimb", repr(exc))
        state.cimb_rate = None
    else:
        health.ok("cimb")
        state.cimb_rate, state.cimb_at = rate, now
        db.record_rate("cimb", rate, now)

    if fetchers.wise_live is not None:
        try:
            wise = await fetchers.wise_live()
        except Exception as exc:
            health.failed("wise", repr(exc))
            state.wise_rate = None
        else:
            health.ok("wise")
            state.wise_rate, state.wise_at = wise, now
            db.record_rate("wise", wise, now)

    today = now.astimezone(TIMEZONE).date()
    if fetchers.wise_fee is not None and state.fee_checked_on != today:
        state.fee_checked_on = today  # once per day, even if it fails
        try:
            fee = await fetchers.wise_fee(ALERT_REFERENCE_SGD)
        except Exception as exc:
            health.failed("wise fee", repr(exc))
        else:
            health.ok("wise fee")
            state.wise_fee = fee
            db.save_wise_fee(fee, now)


async def evaluate_users(db: Database, sender: AlertSender, state: RateState, now: datetime) -> None:
    quotes = quotes_for(state, ALERT_REFERENCE_SGD)
    if not quotes:
        return
    best = quotes[0].effective_rate
    for user in db.list_users():
        decision = decide(user, best, now)
        if decision == "reset":
            db.update_user(user.discord_user_id, peak_rate=0.0)
        elif decision == "alert":
            try:
                sent = await sender.send_alert(user, state)
            except Exception as exc:
                log.error("alert to %s failed: %r", user.discord_user_id, exc)
                sent = False
            if sent:
                db.update_user(user.discord_user_id, peak_rate=best, last_alerted_at=now.isoformat())


async def run_monitor(fetchers: Fetchers, db: Database, state: RateState, sender: AlertSender) -> None:
    health = FetchHealth()
    last_prune: date | None = None
    while True:
        now = datetime.now(timezone.utc)
        if not is_active(now):
            await asyncio.sleep(min(seconds_until_next_window(now), MAX_IDLE_SLEEP_SECONDS))
            continue
        await poll_once(fetchers, db, state, health, now)
        await evaluate_users(db, sender, state, now)
        if last_prune != now.date():
            db.prune(now - timedelta(days=HISTORY_RETENTION_DAYS))
            last_prune = now.date()
        await asyncio.sleep(RATE_POLL_SECONDS)
