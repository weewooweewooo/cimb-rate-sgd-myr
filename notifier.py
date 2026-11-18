"""Send alert DMs (with a history chart when Wise history is available)."""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

import discord

from chart import likely_band, percentile_rank, render_chart
from db import Database
from embeds import alert_preview_text, build_alert_embed
from models import RateState, User
from settings import ALERT_REFERENCE_SGD
from ui import AlertView

log = logging.getLogger(__name__)

HistoryFetcher = Callable[[], Awaitable[list[tuple[datetime, float]]]]
CHART_DAYS = 7


class Notifier:
    def __init__(
        self,
        bot: discord.Client,
        db: Database,
        state: RateState,
        history_fetcher: HistoryFetcher | None = None,
    ):
        self.bot, self.db, self.state = bot, db, state
        self.history_fetcher = history_fetcher

    async def _get_user(self, user_id: str) -> discord.User | None:
        user = self.bot.get_user(int(user_id))
        if user is not None:
            return user
        try:
            return await self.bot.fetch_user(int(user_id))
        except discord.DiscordException as exc:
            log.error("fetch user %s failed: %r", user_id, exc)
            return None

    async def _chart_file(self, user: User, state: RateState, now: datetime) -> discord.File | None:
        if self.history_fetcher is None or state.wise_rate is None:
            return None
        try:
            history = await self.history_fetcher()
            since = now - timedelta(days=CHART_DAYS)
            mid = [point for point in history if point[0] >= since]
            cimb = self.db.rates_since("cimb", since)
            band = likely_band(history, state.wise_rate)
            rank = percentile_rank(history, state.wise_rate)
            png = await asyncio.to_thread(render_chart, mid, cimb, user.target_rate, state.wise_rate, band, rank)
        except Exception as exc:
            log.error("chart skipped: %r", exc)
            return None
        return discord.File(io.BytesIO(png), filename="chart.png")

    async def send_alert(self, user: User, state: RateState) -> bool:
        target = await self._get_user(user.discord_user_id)
        if target is None:
            return False
        now = datetime.now(timezone.utc)
        embed = build_alert_embed(user, state, ALERT_REFERENCE_SGD, now)
        kwargs = {"content": alert_preview_text(state), "embed": embed, "view": AlertView(self.db, state)}
        chart = await self._chart_file(user, state, now)
        if chart is not None:
            embed.set_image(url="attachment://chart.png")
            kwargs["file"] = chart
        try:
            await target.send(**kwargs)
        except discord.DiscordException as exc:
            log.error("DM to %s failed: %r", user.discord_user_id, exc)
            return False
        return True
