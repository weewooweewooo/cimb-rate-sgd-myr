"""Project constants and secret loading.

Only secrets live in .env (DISCORD_BOT_TOKEN, DISCORD_GUILD_ID).
Everything else that tunes the bot is a constant here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Schedule: Mon-Fri, 09:00 (inclusive) to 20:00 (exclusive), Singapore time.
TIMEZONE = ZoneInfo("Asia/Singapore")
ALERT_DAYS = (0, 1, 2, 3, 4)  # datetime.weekday(): Monday == 0
ALERT_START = time(9, 0)
ALERT_END = time(20, 0)

# Polling and HTTP.
RATE_POLL_SECONDS = 60
HTTP_TIMEOUT_SECONDS = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Providers.
CIMB_RATE_URL = "https://www.cimbclicks.com.sg/sgd-to-myr"
WISE_LIVE_URL = "https://wise.com/rates/live"
WISE_PRICE_URL = "https://wise.com/gateway/v1/price"
WISE_HISTORY_URL = "https://wise.com/rates/history+live"
WISE_SEND_URL = "https://wise.com/send"
WISE_DEFAULT_FEE_PCT = 0.0025
WISE_DEFAULT_FEE_FIXED_SGD = 0.53
WISE_ALLOWED_PAYINS = ("PAYNOW", "RECEIVE_BANK_TRANSFER", "FAST_DIRECT_DEBIT")

# Comparison and alerting.
ALERT_REFERENCE_SGD = 1000.0
COMPARE_PRESETS = (200, 500, 1000, 2000, 3000)
AMOUNT_MIN_SGD = 10.0
AMOUNT_MAX_SGD = 100_000.0
REALERT_STEP = 0.0010
SNOOZE_MINUTES = 60
DEFAULT_TARGET = 3.1000

# Storage.
DB_PATH = "data/rates.db"
LEGACY_CONFIG_DIR = "config"
HISTORY_RETENTION_DAYS = 90


@dataclass(frozen=True)
class Secrets:
    discord_bot_token: str
    discord_guild_id: int | None


def load_secrets() -> Secrets:
    load_dotenv()
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required")
    guild = os.getenv("DISCORD_GUILD_ID", "").strip()
    return Secrets(token, int(guild) if guild else None)
