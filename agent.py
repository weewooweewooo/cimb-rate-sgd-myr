from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz
from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright

from bot import build_bot
from config_loader import ConfigLoader
from notifier import AlertPayload, DiscordNotifier

RATE_JS = """
() => {
    try {
        const val = getObject(encodeNamespace('rateList'))?.value;
        if (!val) return null;
        const parsed = JSON.parse(val);
        return Array.isArray(parsed) && parsed.length > 0 ? parsed[0] : null;
    } catch(e) {
        return null;
    }
}
"""

RATE_LIST_READY_JS = """
() => {
    try {
        const val = getObject(encodeNamespace('rateList'))?.value;
        if (!val) return false;
        const parsed = JSON.parse(val);
        return Array.isArray(parsed) && parsed.length > 0;
    } catch(e) {
        return false;
    }
}
"""


# Store environment settings used by the agent.
@dataclass
class Settings:
    discord_bot_token: str
    scrape_interval_ms: int
    idle_sleep_ms: int
    max_null_streak: int
    timezone_name: str
    cimb_rate_url: str
    config_dir: str
    page_reload_interval_ms: int


# Read environment variables into typed settings.
def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        discord_bot_token=os.getenv("DISCORD_BOT_TOKEN", "").strip(),
        scrape_interval_ms=int(os.getenv("SCRAPE_INTERVAL_MS", "3000")),
        idle_sleep_ms=int(os.getenv("IDLE_SLEEP_MS", "60000")),
        max_null_streak=int(os.getenv("MAX_NULL_STREAK", "5")),
        timezone_name=os.getenv("TIMEZONE", "Asia/Singapore").strip()
        or "Asia/Singapore",
        cimb_rate_url=os.getenv(
            "CIMB_RATE_URL", "https://www.cimbclicks.com.sg/sgd-to-myr"
        ).strip(),
        config_dir=os.getenv("CONFIG_DIR", "config").strip() or "config",
        page_reload_interval_ms=int(os.getenv("PAGE_RELOAD_INTERVAL_MS", "300000")),
    )


# Convert the scraped raw value into a numeric rate.
def parse_rate_value(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"(\d+(?:\.\d+)?)", str(raw).replace(",", ""))
    return float(match.group(1)) if match else None


# Parse a 24-hour HH:MM string.
def parse_hhmm(value: str) -> Optional[tuple[int, int]]:
    match = re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", str(value))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


# Check whether a local time is inside a configured active window.
def is_within_active_window(
    now_local: datetime, active_start: str, active_end: str
) -> bool:
    start_parts = parse_hhmm(active_start)
    end_parts = parse_hhmm(active_end)
    if not start_parts or not end_parts:
        return False
    start_minutes = start_parts[0] * 60 + start_parts[1]
    end_minutes = end_parts[0] * 60 + end_parts[1]
    current_minutes = now_local.hour * 60 + now_local.minute
    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes <= end_minutes
    return current_minutes >= start_minutes or current_minutes <= end_minutes


# Check whether today is enabled for alerts.
def is_active_day(now_local: datetime, active_days: list) -> bool:
    day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    today = day_names[now_local.weekday()]
    return today in [str(day).lower().strip() for day in active_days]


# Check whether at least one enabled user can receive alerts now.
def any_user_active(users: List[Dict[str, Any]], now_local: datetime) -> bool:
    for user in users:
        active_days = user.get("active_days", ["mon", "tue", "wed", "thu", "fri"])
        active_start = str(user.get("active_start", "00:00"))
        active_end = str(user.get("active_end", "23:59"))
        if not user.get("enabled", False):
            continue
        if not is_active_day(now_local, active_days):
            continue
        if is_within_active_window(now_local, active_start, active_end):
            return True
    return False


# Fetch the current exchange rate from the page JavaScript.
async def fetch_live_rate(page: Page) -> Optional[float]:
    return parse_rate_value(await page.evaluate(RATE_JS))


# Return a timezone-aware UTC timestamp.
def utc_now() -> datetime:
    return datetime.utcnow().replace(tzinfo=pytz.UTC)


# Wait until the CIMB page has rate data available.
async def wait_for_rate_list(page: Page) -> None:
    await page.wait_for_function(RATE_LIST_READY_JS, timeout=60000)


# Open a browser context configured for the CIMB page.
async def open_browser_context(playwright: Any) -> tuple[Any, Any]:
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-gpu",
        ],
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
        locale="en-SG",
    )
    return browser, context


# Load the CIMB rate page before polling begins.
async def open_rate_page(context: Any, settings: Settings) -> Page:
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(settings.cimb_rate_url, wait_until="networkidle")
    await wait_for_rate_list(page)
    print("[agent] rateList ready")
    return page


# Reload the CIMB page when cached data may be stale.
async def reload_rate_page(page: Page) -> None:
    await page.reload(wait_until="networkidle")
    await wait_for_rate_list(page)
    print("[agent] page reloaded")


# Start Discord and create the notifier used by the scraper.
async def start_bot(
    settings: Settings,
    config_loader: ConfigLoader,
    shared_state: Dict[str, Any],
) -> tuple[Any, DiscordNotifier, asyncio.Task[None]]:
    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required")

    discord_bot = build_bot(config_loader, lambda: dict(shared_state))
    notifier = DiscordNotifier(discord_bot)
    bot_task = asyncio.create_task(
        discord_bot.start(settings.discord_bot_token), name="discord-bot"
    )
    await asyncio.sleep(0)
    await discord_bot.wait_until_ready()
    print("[agent] bot ready - starting scrape loop")
    return discord_bot, notifier, bot_task


# Stop Discord cleanly during shutdown.
async def stop_bot(discord_bot: Any, bot_task: asyncio.Task[None]) -> None:
    await discord_bot.close()
    if bot_task.done():
        return
    bot_task.cancel()
    try:
        await bot_task
    except asyncio.CancelledError:
        pass


# Log a rate value only when it changes.
def log_rate_if_changed(
    timestamp: datetime,
    rate: float,
    sleep_ms: int,
    user_count: int,
    last_logged_rate: Optional[float],
) -> Optional[float]:
    if rate == last_logged_rate:
        return last_logged_rate
    print(
        f"[{timestamp.isoformat()}] rate={rate:.4f} "
        f"next_sleep_ms={sleep_ms} users={user_count}"
    )
    return rate


# Fetch one rate reading and update shared state.
async def run_scrape_cycle(
    page: Page,
    users: List[Dict[str, Any]],
    timestamp: datetime,
    null_streak: int,
    settings: Settings,
    shared_state: Dict[str, Any],
) -> tuple[Optional[float], int]:
    try:
        rate = await fetch_live_rate(page)
    except Exception as exc:
        print(f"[agent] scrape error: {exc}")
        rate = None

    if rate is not None:
        shared_state.update({"rate": rate, "timestamp": timestamp.isoformat()})
        return rate, 0

    null_streak = await handle_null_rate(page, users, timestamp, null_streak, settings)
    shared_state.update({"rate": None, "timestamp": timestamp.isoformat()})
    return None, null_streak


# Reload after repeated null readings and report the failed read.
async def handle_null_rate(
    page: Page,
    users: List[Dict[str, Any]],
    timestamp: datetime,
    null_streak: int,
    settings: Settings,
) -> int:
    null_streak += 1
    if null_streak >= settings.max_null_streak:
        print(f"[agent] warning: {null_streak} consecutive null reads - reloading page")
        await page.reload(wait_until="domcontentloaded")
        null_streak = 0
    print(
        f"[{timestamp.isoformat()}] rate=None "
        f"next_sleep_ms={settings.scrape_interval_ms} users={len(users)}"
    )
    return null_streak


# Check whether a user can receive an alert at the current time.
def user_is_active_now(user: Dict[str, Any], now_local: datetime) -> bool:
    active_start = str(user.get("active_start", "00:00"))
    active_end = str(user.get("active_end", "23:59"))
    active_days = user.get("active_days", ["mon", "tue", "wed", "thu", "fri"])
    return is_active_day(now_local, active_days) and is_within_active_window(
        now_local, active_start, active_end
    )


# Send one user's alert and persist the new peak.
async def send_peak_alert(
    user: Dict[str, Any],
    rate: float,
    target: float,
    timestamp: datetime,
    config_loader: ConfigLoader,
    notifier: DiscordNotifier,
) -> None:
    discord_user_id = str(user.get("discord_user_id"))
    payload = AlertPayload(
        discord_user_id=discord_user_id,
        user_name=str(user.get("name", "User")),
        rate=rate,
        target_rate=target,
        active_start=str(user.get("active_start", "00:00")),
        active_end=str(user.get("active_end", "23:59")),
    )
    if await notifier.send_rate_alert(payload):
        await config_loader.update_user_fields(
            discord_user_id,
            {"peak_rate": rate, "last_alerted_at": timestamp.isoformat()},
        )


# Apply peak tracking rules for one user.
async def process_user_alert(
    user: Dict[str, Any],
    rate: float,
    timestamp: datetime,
    now_local: datetime,
    config_loader: ConfigLoader,
    notifier: DiscordNotifier,
) -> None:
    if not user.get("enabled", False):
        return
    target = float(user.get("target_rate", 0.0))
    peak_rate = float(user.get("peak_rate", 0.0))
    discord_user_id = str(user.get("discord_user_id"))
    if target <= 0:
        return
    if rate < target:
        if peak_rate > 0:
            await config_loader.update_user_fields(discord_user_id, {"peak_rate": 0.0})
        return
    if rate <= peak_rate or not user_is_active_now(user, now_local):
        return
    await send_peak_alert(user, rate, target, timestamp, config_loader, notifier)


# Apply peak tracking rules for all loaded users.
async def process_user_alerts(
    users: List[Dict[str, Any]],
    rate: float,
    timestamp: datetime,
    now_local: datetime,
    config_loader: ConfigLoader,
    notifier: DiscordNotifier,
) -> None:
    for user in users:
        try:
            await process_user_alert(
                user, rate, timestamp, now_local, config_loader, notifier
            )
        except Exception as exc:
            print(f"[agent] user-processing error: {exc}")


# Reload the page if the configured reload interval has elapsed.
async def reload_if_due(
    page: Page, timestamp: datetime, last_reload_at: datetime, settings: Settings
) -> datetime:
    elapsed_ms = (timestamp - last_reload_at).total_seconds() * 1000
    if elapsed_ms < settings.page_reload_interval_ms:
        return last_reload_at
    await reload_rate_page(page)
    return timestamp


# Process one active polling cycle and sleep until the next one.
async def poll_active_users(
    page: Page, users: List[Dict[str, Any]], timestamp: datetime, now_local: datetime, state: Dict[str, Any]
) -> tuple[int, Optional[float]]:
    settings = state["settings"]
    rate, null_streak = await run_scrape_cycle(
        page, users, timestamp, state["null_streak"], settings, state["shared_state"]
    )
    if rate is not None:
        state["last_logged_rate"] = log_rate_if_changed(
            timestamp, rate, settings.scrape_interval_ms, len(users), state["last_logged_rate"]
        )
        await process_user_alerts(
            users, rate, timestamp, now_local, state["config_loader"], state["notifier"]
        )
    await asyncio.sleep(settings.scrape_interval_ms / 1000)
    return null_streak, state["last_logged_rate"]


# Poll the rate page forever.
async def poll_forever(page: Page, settings: Settings, config_loader: ConfigLoader, notifier: DiscordNotifier, shared_state: Dict[str, Any]) -> None:
    timezone = pytz.timezone(settings.timezone_name)
    last_reload_at = utc_now()
    state = {"config_loader": config_loader, "last_logged_rate": None}
    state.update({"notifier": notifier, "null_streak": 0})
    state.update({"settings": settings, "shared_state": shared_state})

    while True:
        timestamp = utc_now()
        users = await config_loader.get_all_users()
        now_local = timestamp.astimezone(timezone)
        last_reload_at = await reload_if_due(
            page, timestamp, last_reload_at, settings
        )
        if not any_user_active(users, now_local):
            await sleep_idle(timestamp, settings)
            continue
        state["null_streak"], state["last_logged_rate"] = await poll_active_users(
            page, users, timestamp, now_local, state
        )


# Sleep longer when no user is currently active.
async def sleep_idle(timestamp: datetime, settings: Settings) -> None:
    print(
        f"[{timestamp.isoformat()}] all users outside window - "
        f"sleeping {settings.idle_sleep_ms}ms"
    )
    await asyncio.sleep(settings.idle_sleep_ms / 1000)


# Main scraping loop: poll rate, check users, send alerts.
async def run_agent_loop(settings: Settings, config_loader: ConfigLoader) -> None:
    shared_state: Dict[str, Any] = {"rate": None, "timestamp": "N/A"}
    discord_bot, notifier, bot_task = await start_bot(
        settings, config_loader, shared_state
    )
    try:
        async with async_playwright() as playwright:
            browser, context = await open_browser_context(playwright)
            try:
                page = await open_rate_page(context, settings)
                await poll_forever(
                    page, settings, config_loader, notifier, shared_state
                )
            finally:
                await context.close()
                await browser.close()
    finally:
        await stop_bot(discord_bot, bot_task)


# Initialize settings and config before running the agent.
async def main() -> None:
    settings = load_settings()
    config_loader = ConfigLoader(config_dir=settings.config_dir)
    await config_loader.start()
    try:
        await run_agent_loop(settings, config_loader)
    finally:
        await config_loader.stop()


if __name__ == "__main__":
    asyncio.run(main())
