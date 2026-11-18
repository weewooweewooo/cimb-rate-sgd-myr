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


NOTICE_AFTER = timedelta(minutes=15)
# provider -> (display name, the provider alerts fall back to)
NOTICE_PROVIDERS = {"cimb": ("CIMB", "Wise"), "wise": ("Wise", "CIMB")}


class FetchHealth:
    """Log a provider failure once per outage, and once on recovery.

    Also queues one DM-able notice when a provider has been failing for
    NOTICE_AFTER, and a recovery notice once it's back.
    """

    def __init__(self) -> None:
        self._failing_since: dict[str, datetime] = {}
        self._notified: set[str] = set()
        self._pending: list[str] = []

    def ok(self, name: str, now: datetime | None = None) -> None:
        if self._failing_since.pop(name, None) is None:
            return
        log.warning("%s fetch recovered", name)
        if name in self._notified:
            self._notified.discard(name)
            label, _ = NOTICE_PROVIDERS[name]
            self._pending.append(f"{label}'s rate is readable again. Alerts are back to normal.")

    def failed(self, name: str, detail: str, now: datetime | None = None) -> None:
        if name not in self._failing_since:
            self._failing_since[name] = now or datetime.now(timezone.utc)
            log.error("%s fetch failing: %s", name, detail)

    def due_notices(self, now: datetime) -> list[str]:
        for name, since in self._failing_since.items():
            if name in NOTICE_PROVIDERS and name not in self._notified and now - since >= NOTICE_AFTER:
                self._notified.add(name)
                label, fallback = NOTICE_PROVIDERS[name]
                self._pending.append(
                    f"Heads-up: the bot hasn't been able to read {label}'s rate for 15 minutes. "
                    f"Alerts use {fallback} only until it's back."
                )
        notices, self._pending = self._pending, []
        return notices


@dataclass
class Fetchers:
    cimb: Callable[[], Awaitable[float]]
    wise_live: Callable[[], Awaitable[float]] | None = None
    wise_fee: Callable[[float], Awaitable[WiseFee]] | None = None


class AlertSender(Protocol):
    async def send_alert(self, user: User, state: RateState) -> bool: ...

    async def send_notice(self, text: str) -> None: ...


async def notify_health(health: FetchHealth, sender: AlertSender, now: datetime) -> None:
    for text in health.due_notices(now):
        try:
            await sender.send_notice(text)
        except Exception as exc:
            log.error("notice failed: %r", exc)


async def poll_once(
    fetchers: Fetchers, db: Database, state: RateState, health: FetchHealth, now: datetime
) -> None:
    try:
        rate = await fetchers.cimb()
    except Exception as exc:  # one provider must never stop the loop
        health.failed("cimb", repr(exc), now)
        state.cimb_rate = None
    else:
        health.ok("cimb", now)
        state.cimb_rate, state.cimb_at = rate, now
        db.record_rate("cimb", rate, now)

    if fetchers.wise_live is not None:
        try:
            wise = await fetchers.wise_live()
        except Exception as exc:
            health.failed("wise", repr(exc), now)
            state.wise_rate = None
        else:
            health.ok("wise", now)
            state.wise_rate, state.wise_at = wise, now
            db.record_rate("wise", wise, now)

    today = now.astimezone(TIMEZONE).date()
    if fetchers.wise_fee is not None and state.fee_checked_on != today:
        state.fee_checked_on = today  # once per day, even if it fails
        try:
            fee = await fetchers.wise_fee(ALERT_REFERENCE_SGD)
        except Exception as exc:
            health.failed("wise fee", repr(exc), now)
        else:
            health.ok("wise fee", now)
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
        await notify_health(health, sender, now)
        if last_prune != now.date():
            db.prune(now - timedelta(days=HISTORY_RETENTION_DAYS))
            last_prune = now.date()
        await asyncio.sleep(RATE_POLL_SECONDS)
