"""Send alert DMs."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord

from db import Database
from embeds import alert_preview_text, build_alert_embed
from models import RateState, User
from settings import ALERT_REFERENCE_SGD
from ui import AlertView

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, bot: discord.Client, db: Database, state: RateState):
        self.bot, self.db, self.state = bot, db, state

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
        try:
            await target.send(
                content=alert_preview_text(state),
                embed=build_alert_embed(user, state, ALERT_REFERENCE_SGD, now),
                view=AlertView(self.db, state),
            )
        except discord.DiscordException as exc:
            log.error("DM to %s failed: %r", user.discord_user_id, exc)
            return False
        return True
