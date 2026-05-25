from __future__ import annotations

from dataclasses import dataclass

import discord


# Store user and rate data needed for alert DMs.
@dataclass
class AlertPayload:
    discord_user_id: str
    user_name: str
    rate: float
    target_rate: float
    active_start: str
    active_end: str


# Send Discord DM alerts for qualifying rates.
class DiscordNotifier:
    # Store the Discord client used for user lookup and DMs.
    def __init__(self, bot: discord.Client):
        self.bot = bot

    # Resolve a Discord user from cache or API.
    async def _get_user(self, discord_user_id: str) -> discord.User | None:
        user = self.bot.get_user(int(discord_user_id))
        if user is not None:
            return user
        try:
            return await self.bot.fetch_user(int(discord_user_id))
        except Exception as exc:
            print(f"[notifier] fetch user failed {discord_user_id}: {exc}")
            return None

    # Build the rate alert embed.
    def _build_embed(self, payload: AlertPayload) -> discord.Embed:
        embed = discord.Embed(
            title="SGD \u2192 MYR Rate Alert",
            color=discord.Color.from_rgb(226, 75, 74),
        )
        embed.add_field(name="Live Rate", value=f"**{payload.rate:.4f}**", inline=True)
        embed.add_field(
            name="Your Target", value=f"{payload.target_rate:.4f}", inline=True
        )
        embed.add_field(
            name="Active Window",
            value=f"{payload.active_start} \u2013 {payload.active_end}",
            inline=False,
        )
        embed.set_footer(text="Open CIMB app to transfer now \u00b7 SGD \u2192 MYR")
        return embed

    # Send a rate alert embed to a user's DM.
    async def send_rate_alert(self, payload: AlertPayload) -> bool:
        user = await self._get_user(payload.discord_user_id)
        if user is None:
            return False
        try:
            await user.send(embed=self._build_embed(payload))
            return True
        except Exception as exc:
            print(f"[notifier] dm failed to {payload.discord_user_id}: {exc}")
            return False
