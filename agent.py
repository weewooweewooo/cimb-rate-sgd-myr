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
from settings import DB_PATH, HTTP_TIMEOUT_SECONDS, LEGACY_CONFIG_DIR, USER_AGENT, load_secrets

log = logging.getLogger("agent")


def make_session() -> aiohttp.ClientSession:
    return aiohttp.ClientSession(
        headers={"User-Agent": USER_AGENT},
        timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS),
    )


def make_fetchers(session: aiohttp.ClientSession) -> Fetchers:
    return Fetchers(cimb=lambda: fetch_cimb_rate(session))


async def check() -> int:
    async with make_session() as session:
        try:
            rate = await fetch_cimb_rate(session)
        except Exception as exc:
            print(f"cimb=ERROR {exc!r}")
            return 1
        print(f"cimb={rate:.4f}")
        return 0


async def run() -> None:
    secrets = load_secrets()
    db = Database(DB_PATH)
    db.import_legacy_configs(LEGACY_CONFIG_DIR)
    state = RateState()
    async with make_session() as session:
        bot = build_bot(db, state, secrets)
        notifier = Notifier(bot, db, state)
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
