from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz
from dotenv import load_dotenv
from playwright.async_api import Page, async_playwright

from bot import build_bot
from config_loader import ConfigLoader
from notifier import AlertBand, AlertPayload, DiscordNotifier


RATE_JS = """
() => {
  const list = getObject(encodeNamespace("rateList"))?.value;
  if (!Array.isArray(list) || list.length === 0) return null;
  return list[0];
}
"""


@dataclass
class Settings:
    discord_bot_token: str
    scrape_interval_normal_ms: int
    scrape_interval_near_ms: int
    scrape_interval_critical_ms: int
    idle_sleep_ms: int
    max_null_streak: int
    timezone_name: str
    cimb_rate_url: str
    browser_data_dir: str
    config_dir: str


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        discord_bot_token=os.getenv("DISCORD_BOT_TOKEN", "").strip(),
        scrape_interval_normal_ms=int(os.getenv("SCRAPE_INTERVAL_NORMAL_MS", "3000")),
        scrape_interval_near_ms=int(os.getenv("SCRAPE_INTERVAL_NEAR_MS", "800")),
        scrape_interval_critical_ms=int(os.getenv("SCRAPE_INTERVAL_CRITICAL_MS", "200")),
        idle_sleep_ms=int(os.getenv("IDLE_SLEEP_MS", "60000")),
        max_null_streak=int(os.getenv("MAX_NULL_STREAK", "5")),
        timezone_name=os.getenv("TIMEZONE", "Asia/Singapore").strip() or "Asia/Singapore",
        cimb_rate_url=os.getenv("CIMB_RATE_URL", "https://www.cimbclicks.com.sg/sgd-to-myr").strip(),
        browser_data_dir=os.getenv("PLAYWRIGHT_USER_DATA_DIR", ".playwright").strip() or ".playwright",
        config_dir=os.getenv("CONFIG_DIR", "config").strip() or "config",
    )


def parse_rate_value(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw)
    match = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    if not match:
        return None
    return float(match.group(1))


def parse_hhmm(value: str) -> Optional[tuple[int, int]]:
    m = re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", str(value))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def is_within_active_window(now_local: datetime, active_start: str, active_end: str) -> bool:
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


def any_user_active(users: List[Dict[str, Any]], now_local: datetime) -> bool:
    for user in users:
        if not bool(user.get("enabled", False)):
            continue
        active_start = str(user.get("active_start", "00:00"))
        active_end = str(user.get("active_end", "23:59"))
        if is_within_active_window(now_local, active_start, active_end):
            return True
    return False


def parse_timestamp(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return pytz.UTC.localize(parsed)
        return parsed.astimezone(pytz.UTC)
    except Exception:
        return None


def determine_band(rate: float, users: List[Dict[str, Any]]) -> str:
    band = AlertBand.NORMAL
    for user in users:
        if not bool(user.get("enabled", False)):
            continue
        target = float(user.get("target_rate", 0.0))
        buffer_value = abs(float(user.get("buffer", 0.0)))
        if target <= 0 or buffer_value <= 0:
            continue
        distance = abs(target - rate)
        if distance <= buffer_value:
            return AlertBand.CRITICAL
        if distance <= buffer_value * 3:
            band = AlertBand.NEAR
    return band


def band_to_sleep_ms(band: str, settings: Settings) -> int:
    if band == AlertBand.CRITICAL:
        return settings.scrape_interval_critical_ms
    if band == AlertBand.NEAR:
        return settings.scrape_interval_near_ms
    return settings.scrape_interval_normal_ms


async def fetch_live_rate(page: Page) -> Optional[float]:
    raw = await page.evaluate(RATE_JS)
    return parse_rate_value(raw)


async def run_agent_loop(settings: Settings, config_loader: ConfigLoader) -> None:
    tz = pytz.timezone(settings.timezone_name)

    shared_state: Dict[str, Any] = {
        "rate": None,
        "band": AlertBand.NORMAL,
        "timestamp": "N/A",
    }

    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required")

    bot = build_bot(config_loader, lambda: dict(shared_state))
    notifier = DiscordNotifier(bot)

    bot_task = asyncio.create_task(bot.start(settings.discord_bot_token), name="discord-bot")
    await bot.wait_until_ready()
    print("[agent] bot ready — starting scrape loop")

    try:
        async with async_playwright() as playwright:
            Path(settings.browser_data_dir).mkdir(parents=True, exist_ok=True)
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=settings.browser_data_dir,
                headless=True,
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(settings.cimb_rate_url, wait_until="domcontentloaded")
                null_streak = 0

                while True:
                    timestamp = datetime.utcnow().replace(tzinfo=pytz.UTC)
                    users = await config_loader.get_all_users()
                    now_local = timestamp.astimezone(tz)

                    if not any_user_active(users, now_local):
                        print(
                            f"[{timestamp.isoformat()}] all users outside window — "
                            f"sleeping {settings.idle_sleep_ms}ms"
                        )
                        await asyncio.sleep(settings.idle_sleep_ms / 1000)
                        continue

                    rate: Optional[float] = None
                    try:
                        rate = await fetch_live_rate(page)
                    except Exception as exc:
                        print(f"[agent] scrape error: {exc}")

                    if rate is None:
                        null_streak += 1
                        if null_streak >= settings.max_null_streak:
                            print(
                                f"[agent] warning: {null_streak} consecutive null reads — reloading page"
                            )
                            await page.reload(wait_until="domcontentloaded")
                            null_streak = 0
                    else:
                        null_streak = 0

                    if rate is None:
                        band = AlertBand.NORMAL
                        sleep_ms = settings.scrape_interval_normal_ms
                        shared_state.update({"rate": None, "band": band, "timestamp": timestamp.isoformat()})
                        print(
                            f"[{timestamp.isoformat()}] rate=None band={band} "
                            f"next_sleep_ms={sleep_ms} users={len(users)}"
                        )
                        await asyncio.sleep(sleep_ms / 1000)
                        continue

                    band = determine_band(rate, users)
                    sleep_ms = band_to_sleep_ms(band, settings)
                    shared_state.update({"rate": rate, "band": band, "timestamp": timestamp.isoformat()})

                    print(
                        f"[{timestamp.isoformat()}] rate={rate:.4f} band={band} "
                        f"next_sleep_ms={sleep_ms} users={len(users)}"
                    )

                    for user in users:
                        try:
                            if not bool(user.get("enabled", False)):
                                continue
                            target = float(user.get("target_rate", 0.0))
                            if target <= 0:
                                continue
                            if rate < target:
                                continue
                            active_start = str(user.get("active_start", "00:00"))
                            active_end = str(user.get("active_end", "23:59"))
                            if not is_within_active_window(now_local, active_start, active_end):
                                continue
                            cooldown_minutes = int(user.get("cooldown_minutes", 0))
                            last_alerted = parse_timestamp(user.get("last_alerted_at"))
                            if last_alerted is not None and cooldown_minutes > 0:
                                next_allowed = last_alerted + timedelta(minutes=cooldown_minutes)
                                if timestamp < next_allowed:
                                    continue
                            payload = AlertPayload(
                                discord_user_id=str(user.get("discord_user_id")),
                                user_name=str(user.get("name", "User")),
                                rate=rate,
                                target_rate=target,
                                band=band,
                                active_start=active_start,
                                active_end=active_end,
                            )
                            sent = await notifier.send_rate_alert(payload)
                            if sent:
                                await config_loader.update_user_fields(
                                    str(user.get("discord_user_id")),
                                    {"last_alerted_at": timestamp.isoformat()},
                                )
                        except Exception as exc:
                            print(f"[agent] user-processing error: {exc}")

                    await asyncio.sleep(sleep_ms / 1000)
            finally:
                await context.close()
    finally:
        await bot.close()
        if not bot_task.done():
            bot_task.cancel()
            try:
                await bot_task
            except asyncio.CancelledError:
                pass


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