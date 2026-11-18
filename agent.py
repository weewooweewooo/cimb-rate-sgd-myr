"""Entrypoint: start the Discord bot and the rate monitor.

    python agent.py          run the bot (systemd runs this)
    python agent.py --check  fetch rates once, print them, exit (no Discord, no DB)
"""
from __future__ import annotations

import asyncio
import logging
import sys

import aiohttp

from bot import build_bot
from db import Database
from models import RateState
from monitor import Fetchers, run_monitor
from notifier import Notifier
from providers.cimb import fetch_cimb_rate
from providers.wise import fetch_wise_fee, fetch_wise_history, fetch_wise_live
from settings import ALERT_REFERENCE_SGD, DB_PATH, HTTP_TIMEOUT_SECONDS, LEGACY_CONFIG_DIR, USER_AGENT, load_secrets

log = logging.getLogger("agent")


def make_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        headers={"User-Agent": USER_AGENT},
        timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS),
    )


def make_fetchers(session: aiohttp.ClientSession) -> Fetchers:
    return Fetchers(
        cimb=lambda: fetch_cimb_rate(session),
        wise_live=lambda: fetch_wise_live(session),
        wise_fee=lambda amount: fetch_wise_fee(session, amount),
    )


HISTORY_DAYS = 30


def make_history_fetcher(session: aiohttp.ClientSession):
    return lambda: fetch_wise_history(session, HISTORY_DAYS)


def initial_state(db: Database) -> RateState:
    state = RateState()
    saved_fee = db.latest_wise_fee()
    if saved_fee is not None:
        state.wise_fee = saved_fee
    return state


async def check() -> int:
    failures = 0
    async with make_session() as session:
        try:
            print(f"cimb={await fetch_cimb_rate(session):.4f}")
        except Exception as exc:
            print(f"cimb=ERROR {exc!r}")
            failures += 1
        try:
            rate = await fetch_wise_live(session)
            fee = await fetch_wise_fee(session, ALERT_REFERENCE_SGD)
            print(f"wise={rate:.5f} fee={fee.fixed_sgd:.2f}+{fee.pct * 100:.2f}%")
        except Exception as exc:
            print(f"wise=ERROR {exc!r}")
            failures += 1
    return 1 if failures else 0


async def run() -> None:
    secrets = load_secrets()
    db = Database(DB_PATH)
    db.import_legacy_configs(LEGACY_CONFIG_DIR)
    state = initial_state(db)
    async with make_session() as session:
        bot = build_bot(db, state, secrets)
        notifier = Notifier(bot, db, state, history_fetcher=make_history_fetcher(session))
        bot_task = asyncio.create_task(bot.start(secrets.discord_bot_token), name="discord-bot")
        ready = asyncio.create_task(bot.wait_until_ready())
        await asyncio.wait({bot_task, ready}, return_when=asyncio.FIRST_COMPLETED)
        if bot_task.done():
            ready.cancel()
            bot_task.result()  # surfaces login errors so systemd restarts us
            return
        print(f"[agent] bot started, {len(db.list_users())} users", flush=True)
        monitor_task = asyncio.create_task(run_monitor(make_fetchers(session), db, state, notifier), name="monitor")
        try:
            done, _ = await asyncio.wait({bot_task, monitor_task}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            monitor_task.cancel()
            await bot.close()


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    if "--check" in sys.argv:
        sys.exit(asyncio.run(check()))
    asyncio.run(run())


if __name__ == "__main__":
    main()
