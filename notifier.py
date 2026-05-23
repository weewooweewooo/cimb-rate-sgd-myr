from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import discord


class AlertBand:
    NORMAL = "NORMAL"
    NEAR = "NEAR"
    CRITICAL = "CRITICAL"


BAND_COLORS = {
    AlertBand.NORMAL: discord.Color.from_rgb(46, 204, 113),
    AlertBand.NEAR: discord.Color.from_rgb(245, 158, 11),
    AlertBand.CRITICAL: discord.Color.from_rgb(226, 75, 74),
}


@dataclass
class AlertPayload:
    discord_user_id: str
    user_name: str
    rate: float
    target_rate: float
    band: str
    active_start: str
    active_end: str


class DiscordNotifier:
    def __init__(self, bot: discord.Client):
        self.bot = bot

    async def send_rate_alert(self, payload: AlertPayload) -> bool:
        user = self.bot.get_user(int(payload.discord_user_id))
        if user is None:
            try:
                user = await self.bot.fetch_user(int(payload.discord_user_id))
            except Exception as exc:
                print(f"[notifier] fetch user failed {payload.discord_user_id}: {exc}")
                return False

        embed = discord.Embed(
            title="SGD → MYR Rate Alert",
            color=BAND_COLORS.get(payload.band, BAND_COLORS[AlertBand.NORMAL]),
        )
        embed.add_field(
            name="Live Rate",
            value=f"**{payload.rate:.4f}**",
            inline=True,
        )
        embed.add_field(
            name="Your Target",
            value=f"{payload.target_rate:.4f}",
            inline=True,
        )
        embed.add_field(
            name="Band",
            value=payload.band,
            inline=True,
        )
        embed.add_field(
            name="Active Window",
            value=f"{payload.active_start} – {payload.active_end}",
            inline=False,
        )
        embed.set_footer(text="Open CIMB app to transfer now · SGD → MYR")

        try:
            await user.send(embed=embed)
            return True
        except Exception as exc:
            print(f"[notifier] dm failed to {payload.discord_user_id}: {exc}")
            return False