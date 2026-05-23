from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

from config_loader import ConfigLoader


NOT_REGISTERED_MESSAGE = "You are not registered. Contact the admin to be added."
HHMM_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _is_valid_hhmm(value: str) -> bool:
    return bool(HHMM_PATTERN.match(value))


class RateCommands(commands.Cog):
    def __init__(self, bot: "RateHunterBot"):
        self.bot = bot

    async def _ensure_dm(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id is not None:
            await interaction.response.send_message(
                "This command is available in DM only.", ephemeral=True
            )
            return False
        return True

    async def _get_user_config(self, interaction: discord.Interaction) -> Optional[Dict[str, Any]]:
        config = await self.bot.config_loader.get_user_by_discord_id(str(interaction.user.id))
        if config is None:
            if interaction.response.is_done():
                await interaction.followup.send(NOT_REGISTERED_MESSAGE, ephemeral=True)
            else:
                await interaction.response.send_message(NOT_REGISTERED_MESSAGE, ephemeral=True)
            return None
        return config

    @app_commands.command(name="status", description="Show current rate and your alert config")
    async def status(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return

        snapshot = self.bot.snapshot_provider()
        rate = snapshot.get("rate")
        band = snapshot.get("band", "NORMAL")
        updated_at = snapshot.get("timestamp", "N/A")
        last_alerted = config.get("last_alerted_at") or "Never"

        lines = [
            f"Live rate: {rate:.4f}" if isinstance(rate, (int, float)) else "Live rate: N/A",
            f"Band: {band}",
            f"Updated at: {updated_at}",
            f"Target: {float(config.get('target_rate', 0.0)):.4f}",
            f"Buffer: {float(config.get('buffer', 0.0)):.4f}",
            f"Window: {config.get('active_start', '00:00')} – {config.get('active_end', '23:59')}",
            f"Enabled: {bool(config.get('enabled', False))}",
            f"Cooldown (minutes): {int(config.get('cooldown_minutes', 0))}",
            f"Last alerted: {last_alerted}",
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="settarget", description="Set your target SGD→MYR rate")
    async def settarget(self, interaction: discord.Interaction, rate: float) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return
        if rate <= 0:
            await interaction.response.send_message("Rate must be greater than 0.", ephemeral=True)
            return
        ok = await self.bot.config_loader.update_user_fields(
            str(interaction.user.id), {"target_rate": round(rate, 4)}
        )
        if not ok:
            await interaction.response.send_message("Failed to update config.", ephemeral=True)
            return
        await interaction.response.send_message(f"Target updated to {rate:.4f}", ephemeral=True)

    @app_commands.command(name="setbuffer", description="Set your alert buffer")
    async def setbuffer(self, interaction: discord.Interaction, value: float) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return
        if value <= 0:
            await interaction.response.send_message("Buffer must be greater than 0.", ephemeral=True)
            return
        ok = await self.bot.config_loader.update_user_fields(
            str(interaction.user.id), {"buffer": round(value, 4)}
        )
        if not ok:
            await interaction.response.send_message("Failed to update config.", ephemeral=True)
            return
        await interaction.response.send_message(f"Buffer updated to {value:.4f}", ephemeral=True)

    @app_commands.command(name="setwindow", description="Set active alert window (HH:MM HH:MM)")
    async def setwindow(self, interaction: discord.Interaction, start: str, end: str) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return
        if not _is_valid_hhmm(start) or not _is_valid_hhmm(end):
            await interaction.response.send_message(
                "Invalid time. Use HH:MM in 24-hour format.", ephemeral=True
            )
            return
        ok = await self.bot.config_loader.update_user_fields(
            str(interaction.user.id), {"active_start": start, "active_end": end}
        )
        if not ok:
            await interaction.response.send_message("Failed to update config.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Active window updated to {start} – {end}", ephemeral=True
        )

    @app_commands.command(name="toggle", description="Enable or disable your alerts")
    @app_commands.describe(mode="Choose on or off")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def toggle(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return
        enabled = mode.value == "on"
        ok = await self.bot.config_loader.update_user_fields(
            str(interaction.user.id), {"enabled": enabled}
        )
        if not ok:
            await interaction.response.send_message("Failed to update config.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Alerts {'enabled' if enabled else 'disabled'}.", ephemeral=True
        )

    @app_commands.command(name="setcooldown", description="Set cooldown between alerts in minutes")
    async def setcooldown(self, interaction: discord.Interaction, minutes: int) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return
        if minutes < 0:
            await interaction.response.send_message(
                "Cooldown must be 0 or greater.", ephemeral=True
            )
            return
        ok = await self.bot.config_loader.update_user_fields(
            str(interaction.user.id), {"cooldown_minutes": minutes}
        )
        if not ok:
            await interaction.response.send_message("Failed to update config.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Cooldown updated to {minutes} minutes.", ephemeral=True
        )


class RateHunterBot(commands.Bot):
    def __init__(
        self,
        config_loader: ConfigLoader,
        snapshot_provider: Callable[[], Dict[str, Any]],
    ):
        intents = discord.Intents.none()
        super().__init__(command_prefix="!", intents=intents)
        self.config_loader = config_loader
        self.snapshot_provider = snapshot_provider

    async def setup_hook(self) -> None:
        await self.add_cog(RateCommands(self))
        synced = await self.tree.sync()
        print(f"[bot] synced {len(synced)} global slash command(s)")

    async def on_ready(self) -> None:
        print(f"[bot] logged in as {self.user} at {datetime.utcnow().isoformat()}Z")


def build_bot(
    config_loader: ConfigLoader,
    snapshot_provider: Callable[[], Dict[str, Any]],
) -> RateHunterBot:
    return RateHunterBot(config_loader=config_loader, snapshot_provider=snapshot_provider)