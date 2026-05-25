from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from config_loader import ConfigLoader

NOT_REGISTERED_MESSAGE = "You are not registered. Contact the admin to be added."
HHMM_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


# Check if a string matches HH:MM 24-hour time format
def _is_valid_hhmm(value: str) -> bool:
    return bool(HHMM_PATTERN.match(value))


# Format exchange rate as 4-decimal string or N/A if None
def _format_live_rate(rate: Any) -> str:
    return f"{rate:.4f}" if isinstance(rate, (int, float)) else "N/A"


# Update user config and send response to Discord interaction
async def _send_update_result(
    interaction: discord.Interaction,
    config_loader: ConfigLoader,
    fields: Dict[str, Any],
    success_message: str,
) -> None:
    ok = await config_loader.update_user_fields(str(interaction.user.id), fields)
    if not ok:
        await interaction.response.send_message(
            "Failed to update config.", ephemeral=True
        )
        return
    await interaction.response.send_message(success_message, ephemeral=True)


# Modal dialog for setting target exchange rate
class SetTargetModal(discord.ui.Modal, title="Set Target Rate"):
    rate = discord.ui.TextInput(
        label="Target SGD->MYR Rate",
        placeholder="e.g. 3.1050",
        required=True,
    )

    def __init__(self, config_loader: ConfigLoader):
        super().__init__()
        self.config_loader = config_loader

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Validate and update target rate value
        try:
            rate = float(str(self.rate.value).strip())
        except ValueError:
            await interaction.response.send_message(
                "Rate must be a number.", ephemeral=True
            )
            return
        if rate <= 0:
            await interaction.response.send_message(
                "Rate must be greater than 0.", ephemeral=True
            )
            return
        await _send_update_result(
            interaction,
            self.config_loader,
            {"target_rate": round(rate, 4)},
            f"Target updated to {rate:.4f}",
        )


# Modal dialog for setting active alert time window
class SetWindowModal(discord.ui.Modal, title="Set Window"):
    start = discord.ui.TextInput(
        label="Start time (HH:MM)",
        placeholder="e.g. 09:00",
        required=True,
    )
    end = discord.ui.TextInput(
        label="End time (HH:MM)",
        placeholder="e.g. 19:00",
        required=True,
    )

    def __init__(self, config_loader: ConfigLoader):
        super().__init__()
        self.config_loader = config_loader

    async def on_submit(self, interaction: discord.Interaction) -> None:
        # Validate time window format and update settings
        start = str(self.start.value).strip()
        end = str(self.end.value).strip()
        if not _is_valid_hhmm(start) or not _is_valid_hhmm(end):
            await interaction.response.send_message(
                "Invalid time. Use HH:MM in 24-hour format.", ephemeral=True
            )
            return
        await _send_update_result(
            interaction,
            self.config_loader,
            {"active_start": start, "active_end": end},
            f"Active window updated to {start} - {end}",
        )


# Modal dialog for toggling alerts on or off
class ToggleModal(discord.ui.Modal, title="Toggle On/Off"):
    mode = discord.ui.TextInput(
        label="Enter on or off",
        placeholder="on",
        required=True,
    )

    def __init__(self, config_loader: ConfigLoader):
        super().__init__()
        self.config_loader = config_loader

    # Parse and validate on/off toggle value
    async def on_submit(self, interaction: discord.Interaction) -> None:
        mode = str(self.mode.value).strip().lower()
        if mode not in {"on", "off"}:
            await interaction.response.send_message(
                "Enter either on or off.", ephemeral=True
            )
            return
        enabled = mode == "on"
        await _send_update_result(
            interaction,
            self.config_loader,
            {"enabled": enabled},
            f"Alerts {'enabled' if enabled else 'disabled'}.",
        )


# Interactive button-based day selector for setting active days of the week
class DaySelectView(discord.ui.View):
    DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    DAY_LABELS = {
        "mon": "Mon",
        "tue": "Tue",
        "wed": "Wed",
        "thu": "Thu",
        "fri": "Fri",
        "sat": "Sat",
        "sun": "Sun",
    }

    def __init__(self, config_loader, discord_user_id, active_days):
        super().__init__(timeout=120)
        self.config_loader = config_loader
        self.discord_user_id = discord_user_id
        # Copy the current active days as a mutable set
        self.selected = set(active_days)
        # Add all 7 day toggle buttons dynamically
        self._build_buttons()

    def _build_buttons(self):
        # Clear existing buttons first
        self.clear_items()
        # Add one button per day
        for day in self.DAYS:
            is_active = day in self.selected
            button = discord.ui.Button(
                label=f"{'✅' if is_active else '❌'} {self.DAY_LABELS[day]}",
                style=(
                    discord.ButtonStyle.success
                    if is_active
                    else discord.ButtonStyle.secondary
                ),
                custom_id=f"day_{day}",
                row=0 if self.DAYS.index(day) < 4 else 1,
            )
            button.callback = self._make_toggle_callback(day)
            self.add_item(button)
        # Add Save button on row 2
        save_button = discord.ui.Button(
            label="Save",
            style=discord.ButtonStyle.primary,
            custom_id="save_days",
            row=2,
        )
        save_button.callback = self._save_callback
        self.add_item(save_button)

    def _make_toggle_callback(self, day: str):
        # Returns a callback that toggles the given day
        async def callback(interaction: discord.Interaction):
            if day in self.selected:
                self.selected.discard(day)
            else:
                self.selected.add(day)
            # Prevent deselecting all days
            if not self.selected:
                self.selected.add(day)
                await interaction.response.send_message(
                    "You must have at least one day selected.", ephemeral=True
                )
                return
            # Rebuild buttons to reflect new state
            self._build_buttons()
            await interaction.response.edit_message(
                content=self._status_text(), view=self
            )

        return callback

    async def _save_callback(self, interaction: discord.Interaction):
        # Save selected days to user config
        days_list = [d for d in self.DAYS if d in self.selected]
        ok = await self.config_loader.update_user_fields(
            self.discord_user_id, {"active_days": days_list}
        )
        if not ok:
            await interaction.response.send_message(
                "Failed to save days.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content=f"✅ Active days saved: {', '.join(days_list)}", view=None
        )

    def _status_text(self) -> str:
        # Generate status line showing current selection
        days_list = [d for d in self.DAYS if d in self.selected]
        return (
            f"Select active days (tap to toggle):\n**Active:** {', '.join(days_list)}"
        )


# Interactive button menu for user settings
class MenuView(discord.ui.View):
    def __init__(
        self,
        config_loader: ConfigLoader,
        user_config: Dict[str, Any],
        snapshot: Dict[str, Any],
    ):
        super().__init__(timeout=120)
        self.config_loader = config_loader
        self.user_config = user_config
        self.snapshot = snapshot

    @discord.ui.button(
        label="Set Target Rate", style=discord.ButtonStyle.primary, row=0
    )
    async def set_target(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        # Open modal to set target exchange rate
        await interaction.response.send_modal(SetTargetModal(self.config_loader))

    @discord.ui.button(label="Set Window", style=discord.ButtonStyle.primary, row=0)
    async def set_window(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        # Open modal to set active time window
        await interaction.response.send_modal(SetWindowModal(self.config_loader))

    @discord.ui.button(
        label="Toggle On/Off", style=discord.ButtonStyle.secondary, row=0
    )
    async def toggle(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        # Open modal to enable or disable alerts
        await interaction.response.send_modal(ToggleModal(self.config_loader))

    @discord.ui.button(label="Set Days", style=discord.ButtonStyle.primary, row=1)
    async def set_days(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        # Load current active days from user config
        config = await self.config_loader.get_user_by_discord_id(
            str(interaction.user.id)
        )
        if config is None:
            await interaction.response.send_message(
                "You are not registered.", ephemeral=True
            )
            return
        current_days = config.get("active_days", ["mon", "tue", "wed", "thu", "fri"])
        view = DaySelectView(
            config_loader=self.config_loader,
            discord_user_id=str(interaction.user.id),
            active_days=current_days,
        )
        await interaction.response.send_message(
            view._status_text(),
            view=view,
            ephemeral=True,
        )


# Discord slash commands for rate alerts and configuration
class RateCommands(commands.Cog):
    def __init__(self, bot: "RateHunterBot"):
        self.bot = bot

    # Verify command was issued via direct message
    async def _ensure_dm(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id is not None:
            await interaction.response.send_message(
                "This command is available in DM only.", ephemeral=True
            )
            return False
        return True

    # Retrieve registered user config or notify user if not registered
    async def _get_user_config(
        self, interaction: discord.Interaction
    ) -> Optional[Dict[str, Any]]:
        config = await self.bot.config_loader.get_user_by_discord_id(
            str(interaction.user.id)
        )
        if config is None:
            if interaction.response.is_done():
                await interaction.followup.send(NOT_REGISTERED_MESSAGE, ephemeral=True)
            else:
                await interaction.response.send_message(
                    NOT_REGISTERED_MESSAGE, ephemeral=True
                )
            return None
        return config

    # Create new user registration with default settings

    @app_commands.command(
        name="register", description="Register yourself to receive CIMB rate alerts"
    )
    async def register(self, interaction: discord.Interaction, name: str) -> None:
        if not await self._ensure_dm(interaction):
            return

        discord_user_id = str(interaction.user.id)

        existing = await self.bot.config_loader.get_user_by_discord_id(discord_user_id)
        if existing is not None:
            await interaction.response.send_message(
                f"You are already registered as {existing.get('name')}. "
                f"Use /status to see your current config.",
                ephemeral=True,
            )
            return

        default_config = {
            "name": name,
            "discord_user_id": discord_user_id,
            "target_rate": 3.1000,
            "active_start": "09:00",
            "active_end": "19:00",
            "active_days": ["mon", "tue", "wed", "thu", "fri"],
            "enabled": True,
            "last_alerted_at": None,
            "peak_rate": 0.0,
        }

        ok = await self.bot.config_loader.create_user(discord_user_id, default_config)
        if not ok:
            await interaction.response.send_message(
                "Failed to create your config. Contact the admin.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Registered as **{name}**!\n\n"
            f"Default settings:\n"
            f"Target rate: 3.1000\n"
            f"Active window: 09:00 - 19:00\n\n"
            f"Use /menu to customize your config.",
            ephemeral=True,
        )

    # Display current exchange rate and user's alert configuration

    @app_commands.command(
        name="status", description="Show current rate and your alert config"
    )
    async def status(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return

        snapshot = self.bot.snapshot_provider()
        rate = snapshot.get("rate")
        updated_at = snapshot.get("timestamp", "N/A")
        last_alerted = config.get("last_alerted_at") or "Never"

        lines = [
            f"Live rate: {_format_live_rate(rate)}",
            f"Updated at: {updated_at}",
            f"Target: {float(config.get('target_rate', 0.0)):.4f}",
            f"Window: {config.get('active_start', '00:00')} - {config.get('active_end', '23:59')}",
            f"Active days: {', '.join(config.get('active_days', ['mon', 'tue', 'wed', 'thu', 'fri']))}",
            f"Enabled: {bool(config.get('enabled', False))}",
            f"Peak rate: {float(config.get('peak_rate', 0.0)):.4f}",
            f"Last alerted: {last_alerted}",
        ]
        # Update target exchange rate that triggers alerts
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="settarget", description="Set your target SGD->MYR rate")
    async def settarget(self, interaction: discord.Interaction, rate: float) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return
        if rate <= 0:
            await interaction.response.send_message(
                "Rate must be greater than 0.", ephemeral=True
            )
            return
        ok = await self.bot.config_loader.update_user_fields(
            str(interaction.user.id), {"target_rate": round(rate, 4)}
        )
        if not ok:
            await interaction.response.send_message(
                "Failed to update config.", ephemeral=True
            )
            return
        # Set time window when alerts are allowed
        await interaction.response.send_message(
            f"Target updated to {rate:.4f}", ephemeral=True
        )

    @app_commands.command(
        name="setwindow", description="Set active alert window (HH:MM HH:MM)"
    )
    async def setwindow(
        self, interaction: discord.Interaction, start: str, end: str
    ) -> None:
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
            await interaction.response.send_message(
                "Failed to update config.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            # Enable or disable rate monitoring
            f"Active window updated to {start} - {end}",
            ephemeral=True,
        )

    @app_commands.command(name="toggle", description="Enable or disable your alerts")
    @app_commands.describe(mode="Choose on or off")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def toggle(
        self, interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
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
            await interaction.response.send_message(
                "Failed to update config.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            # Set minimum time between consecutive alerts
            f"Alerts {'enabled' if enabled else 'disabled'}.",
            ephemeral=True,
        )

    # Set which days of the week to receive alerts
    @app_commands.command(
        name="setdays",
        description="Set which days to receive alerts (e.g. mon tue wed thu fri)",
    )
    async def setdays(self, interaction: discord.Interaction, days: str) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return

        allowed = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        # Split by spaces and commas
        raw_days = [
            d.strip().lower() for d in days.replace(",", " ").split() if d.strip()
        ]

        if not raw_days:
            await interaction.response.send_message(
                "Please provide at least one day.", ephemeral=True
            )
            return

        invalid_days = [d for d in raw_days if d not in allowed]
        if invalid_days:
            await interaction.response.send_message(
                f"Invalid days: {', '.join(invalid_days)}. Use: mon tue wed thu fri sat sun",
                ephemeral=True,
            )
            return

        ok = await self.bot.config_loader.update_user_fields(
            str(interaction.user.id), {"active_days": raw_days}
        )
        if not ok:
            await interaction.response.send_message(
                "Failed to update config.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"Active days updated to: {', '.join(raw_days)}", ephemeral=True
        )

    @app_commands.command(
        name="menu", description="Open your CIMB rate alert settings menu"
    )
    async def menu(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return

        snapshot = self.bot.snapshot_provider()
        rate = snapshot.get("rate")
        updated_at = snapshot.get("timestamp", "N/A")

        embed = discord.Embed(title="CIMB Rate Hunter — Your Settings")
        embed.add_field(name="Live rate", value=_format_live_rate(rate), inline=True)
        embed.add_field(name="Updated at", value=str(updated_at), inline=False)
        embed.add_field(
            name="Target",
            value=f"{float(config.get('target_rate', 0.0)):.4f}",
            inline=True,
        )
        embed.add_field(
            name="Window",
            value=f"{config.get('active_start', '00:00')} - {config.get('active_end', '23:59')}",
            inline=True,
        )
        embed.add_field(
            name="Active days",
            value=f"{', '.join(config.get('active_days', ['mon', 'tue', 'wed', 'thu', 'fri']))}",
            inline=True,
        )
        embed.add_field(
            name="Enabled", value=str(bool(config.get("enabled", False))), inline=True
        )
        embed.add_field(
            name="Peak rate",
            value=f"{float(config.get('peak_rate', 0.0)):.4f}",
            inline=True,
        )

        view = MenuView(self.bot.config_loader, config, snapshot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# Discord bot with slash commands and minimal intents
class RateHunterBot(commands.Bot):
    def __init__(
        self,
        config_loader: ConfigLoader,
        snapshot_provider: Callable[[], Dict[str, Any]],
    ):
        intents = discord.Intents.none()
        super().__init__(command_prefix="!", intents=intents)
        self.config_loader = config_loader
        # Load environment and sync slash commands to Discord
        self.snapshot_provider = snapshot_provider

    async def setup_hook(self) -> None:
        load_dotenv()
        await self.add_cog(RateCommands(self))
        synced = await self.tree.sync()
        print(f"[bot] synced {len(synced)} global slash command(s)")

        guild_id = os.getenv("DISCORD_GUILD_ID", "").strip()
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            # Log successful bot connection with timestamp
            guild_synced = await self.tree.sync(guild=guild)
            print(f"[bot] synced {len(guild_synced)} guild slash command(s)")

    async def on_ready(self) -> None:
        print(f"[bot] logged in as {self.user} at {datetime.utcnow().isoformat()}Z")


# Factory function to create and configure the Discord bot
def build_bot(
    config_loader: ConfigLoader,
    snapshot_provider: Callable[[], Dict[str, Any]],
) -> RateHunterBot:
    return RateHunterBot(
        config_loader=config_loader, snapshot_provider=snapshot_provider
    )
