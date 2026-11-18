"""Send alert DMs (with a history chart when one can be drawn)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord

from chart_service import CHART_FILENAME, ChartMaker
from db import Database
from embeds import alert_preview_text, build_alert_embed
from models import RateState, User
from settings import ALERT_REFERENCE_SGD
from ui import AlertView

log = logging.getLogger(__name__)


class Notifier:
    def __init__(
        self,
        bot: discord.Client,
        db: Database,
        state: RateState,
        chart_maker: ChartMaker | None = None,
    ):
        self.bot, self.db, self.state = bot, db, state
        self.chart_maker = chart_maker
        self._failing: set[str] = set()

    async def _get_user(self, user_id: str) -> discord.User | None:
        user = self.bot.get_user(int(user_id))
        if user is not None:
            return user
        try:
            return await self.bot.fetch_user(int(user_id))
        except discord.DiscordException as exc:
            log.error("fetch user %s failed: %r", user_id, exc)
            return None

    async def send_alert(self, user: User, state: RateState) -> bool:
        target = await self._get_user(user.discord_user_id)
        if target is None:
            return False
        now = datetime.now(timezone.utc)
        embed = build_alert_embed(user, state, ALERT_REFERENCE_SGD, now)
        kwargs = {"content": alert_preview_text(state), "embed": embed, "view": AlertView(self.db, state)}
        chart = await self.chart_maker.make(user.target_rate, state, now) if self.chart_maker else None
        if chart is not None:
            embed.set_image(url=f"attachment://{CHART_FILENAME}")
            kwargs["file"] = chart
        try:
            await target.send(**kwargs)
        except discord.DiscordException as exc:
            if user.discord_user_id not in self._failing:  # once per streak, not every minute
                self._failing.add(user.discord_user_id)
                log.error("DM to %s failed: %r", user.discord_user_id, exc)
            return False
        self._failing.discard(user.discord_user_id)
        return True
