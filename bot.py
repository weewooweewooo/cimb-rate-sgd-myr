from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from config_loader import ConfigLoader

NOT_REGISTERED_MESSAGE = "You are not registered. Contact the admin to be added."
DEFAULT_ACTIVE_DAYS = ["mon", "tue", "wed", "thu", "fri"]
ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_LABELS = {
    "mon": "Mon",
    "tue": "Tue",
    "wed": "Wed",
    "thu": "Thu",
    "fri": "Fri",
    "sat": "Sat",
    "sun": "Sun",
}
HHMM_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


# Validate HH:MM values before writing them to config.
def _is_valid_hhmm(value: str) -> bool:
    return bool(HHMM_PATTERN.match(value))


# Format the live rate shown in Discord responses.
def _format_live_rate(rate: Any) -> str:
    return f"{rate:.4f}" if isinstance(rate, (int, float)) else "N/A"


# Build the default config for self-registration.
def _default_user_config(name: str, discord_user_id: str) -> Dict[str, Any]:
    return {
        "name": name,
        "discord_user_id": discord_user_id,
        "target_rate": 3.1000,
        "active_start": "09:00",
        "active_end": "19:00",
        "active_days": list(DEFAULT_ACTIVE_DAYS),
        "enabled": True,
        "last_alerted_at": None,
        "peak_rate": 0.0,
    }


# Create the text returned by the registration command.
def _registration_message(name: str) -> str:
    return (
        f"Registered as **{name}**!\n\n"
        f"Default settings:\n"
        f"Target rate: 3.1000\n"
        f"Active window: 09:00 - 19:00\n\n"
        f"Use /menu to customize your config."
    )


# Build the status command output from current config and snapshot.
def _status_lines(config: Dict[str, Any], snapshot: Dict[str, Any]) -> List[str]:
    last_alerted = config.get("last_alerted_at") or "Never"
    return [
        f"Live rate: {_format_live_rate(snapshot.get('rate'))}",
        f"Updated at: {snapshot.get('timestamp', 'N/A')}",
        f"Target: {float(config.get('target_rate', 0.0)):.4f}",
        f"Window: {config.get('active_start', '00:00')} - {config.get('active_end', '23:59')}",
        f"Active days: {', '.join(config.get('active_days', DEFAULT_ACTIVE_DAYS))}",
        f"Enabled: {bool(config.get('enabled', False))}",
        f"Peak rate: {float(config.get('peak_rate', 0.0)):.4f}",
        f"Last alerted: {last_alerted}",
    ]


# Parse a space- or comma-separated day list.
def _parse_days(days: str) -> tuple[List[str], List[str]]:
    selected_days = [
        day.strip().lower() for day in days.replace(",", " ").split() if day.strip()
    ]
    invalid_days = [day for day in selected_days if day not in ALL_DAYS]
    return selected_days, invalid_days


# Update user config and send a consistent Discord result.
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


# Build the settings embed used by the menu command.
def _build_menu_embed(config: Dict[str, Any], snapshot: Dict[str, Any]) -> discord.Embed:
    embed = discord.Embed(title="CIMB Rate \u2014 Your Settings")
    fields = [
        ("Live rate", _format_live_rate(snapshot.get("rate")), True),
        ("Updated at", str(snapshot.get("timestamp", "N/A")), False),
        ("Target", f"{float(config.get('target_rate', 0.0)):.4f}", True),
        (
            "Window",
            f"{config.get('active_start', '00:00')} - {config.get('active_end', '23:59')}",
            True,
        ),
        ("Active days", ", ".join(config.get("active_days", DEFAULT_ACTIVE_DAYS)), True),
        ("Enabled", str(bool(config.get("enabled", False))), True),
        ("Peak rate", f"{float(config.get('peak_rate', 0.0)):.4f}", True),
    ]
    for name, value, inline in fields:
        embed.add_field(name=name, value=value, inline=inline)
    return embed


# Modal for setting the target exchange rate.
class SetTargetModal(discord.ui.Modal, title="Set Target Rate"):
    rate = discord.ui.TextInput(
        label="Target SGD->MYR Rate",
        placeholder="e.g. 3.1050",
        required=True,
    )

    # Store the config loader for modal submission.
    def __init__(self, config_loader: ConfigLoader):
        super().__init__()
        self.config_loader = config_loader

    # Validate and save the target rate.
    async def on_submit(self, interaction: discord.Interaction) -> None:
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


# Modal for setting the active alert window.
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

    # Store the config loader for modal submission.
    def __init__(self, config_loader: ConfigLoader):
        super().__init__()
        self.config_loader = config_loader

    # Validate and save the active time window.
    async def on_submit(self, interaction: discord.Interaction) -> None:
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


# View for toggling alerts without typed modal input.
class ToggleView(discord.ui.View):
    # Store the toggle target and current state.
    def __init__(
        self, config_loader: ConfigLoader, discord_user_id: str, current_state: bool
    ):
        super().__init__(timeout=60)
        self.config_loader = config_loader
        self.discord_user_id = discord_user_id
        self.current_state = current_state
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = item.label.startswith("\u2705") == self.current_state

    @discord.ui.button(label="\u2705 Enable", style=discord.ButtonStyle.success)
    # Enable alerts for this user.
    async def enable(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self._set_enabled(interaction, True, "\u2705 Alerts enabled.")

    @discord.ui.button(label="\u274c Disable", style=discord.ButtonStyle.danger)
    # Disable alerts for this user.
    async def disable(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await self._set_enabled(interaction, False, "\u274c Alerts disabled.")

    # Persist the selected toggle state.
    async def _set_enabled(
        self, interaction: discord.Interaction, enabled: bool, message: str
    ) -> None:
        ok = await self.config_loader.update_user_fields(
            self.discord_user_id, {"enabled": enabled}
        )
        if not ok:
            await interaction.response.send_message(
                "Failed to update.", ephemeral=True
            )
            return
        await interaction.response.edit_message(content=message, view=None)


# View for selecting active alert days.
class DaySelectView(discord.ui.View):
    # Store the selected days and build the controls.
    def __init__(
        self, config_loader: ConfigLoader, discord_user_id: str, active_days: List[str]
    ):
        super().__init__(timeout=120)
        self.config_loader = config_loader
        self.discord_user_id = discord_user_id
        self.selected = set(active_days)
        self._build_buttons()

    # Build day buttons from the current selection.
    def _build_buttons(self) -> None:
        self.clear_items()
        for index, day in enumerate(ALL_DAYS):
            is_active = day in self.selected
            button = discord.ui.Button(
                label=f"{'\u2705' if is_active else '\u274c'} {DAY_LABELS[day]}",
                style=discord.ButtonStyle.success
                if is_active
                else discord.ButtonStyle.secondary,
                custom_id=f"day_{day}",
                row=0 if index < 4 else 1,
            )
            button.callback = self._make_toggle_callback(day)
            self.add_item(button)
        save_button = discord.ui.Button(
            label="Save", style=discord.ButtonStyle.primary, custom_id="save_days", row=2
        )
        save_button.callback = self._save_callback
        self.add_item(save_button)

    # Create a callback for one day button.
    def _make_toggle_callback(self, day: str) -> Callable[[discord.Interaction], Any]:
        # Toggle one day while preventing an empty selection.
        async def callback(interaction: discord.Interaction) -> None:
            if day in self.selected:
                self.selected.discard(day)
            else:
                self.selected.add(day)
            if not self.selected:
                self.selected.add(day)
                await interaction.response.send_message(
                    "You must have at least one day selected.", ephemeral=True
                )
                return
            self._build_buttons()
            await interaction.response.edit_message(
                content=self._status_text(), view=self
            )

        return callback

    # Save selected days to the user config.
    async def _save_callback(self, interaction: discord.Interaction) -> None:
        days_list = [day for day in ALL_DAYS if day in self.selected]
        ok = await self.config_loader.update_user_fields(
            self.discord_user_id, {"active_days": days_list}
        )
        if not ok:
            await interaction.response.send_message(
                "Failed to save days.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content=f"\u2705 Active days saved: {', '.join(days_list)}", view=None
        )

    # Format the current day selection.
    def _status_text(self) -> str:
        days_list = [day for day in ALL_DAYS if day in self.selected]
        return (
            f"Select active days (tap to toggle):\n**Active:** {', '.join(days_list)}"
        )


# Main settings menu view.
class MenuView(discord.ui.View):
    # Store config access needed by button callbacks.
    def __init__(self, config_loader: ConfigLoader):
        super().__init__(timeout=120)
        self.config_loader = config_loader

    @discord.ui.button(
        label="Set Target Rate", style=discord.ButtonStyle.primary, row=0
    )
    # Open the target-rate modal.
    async def set_target(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(SetTargetModal(self.config_loader))

    @discord.ui.button(label="Set Window", style=discord.ButtonStyle.primary, row=0)
    # Open the active-window modal.
    async def set_window(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(SetWindowModal(self.config_loader))

    @discord.ui.button(
        label="Toggle On/Off", style=discord.ButtonStyle.secondary, row=1
    )
    # Open the toggle button view.
    async def toggle(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        config = await self.config_loader.get_user_by_discord_id(
            str(interaction.user.id)
        )
        if config is None:
            await interaction.response.send_message(
                "You are not registered.", ephemeral=True
            )
            return
        current = bool(config.get("enabled", False))
        view = ToggleView(self.config_loader, str(interaction.user.id), current)
        status = "currently enabled" if current else "currently disabled"
        await interaction.response.send_message(
            f"Alerts are {status}. Choose:", view=view, ephemeral=True
        )

    @discord.ui.button(label="Set Days", style=discord.ButtonStyle.primary, row=1)
    # Open the active-day selection view.
    async def set_days(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ) -> None:
        config = await self.config_loader.get_user_by_discord_id(
            str(interaction.user.id)
        )
        if config is None:
            await interaction.response.send_message(
                "You are not registered.", ephemeral=True
            )
            return
        view = DaySelectView(
            self.config_loader,
            str(interaction.user.id),
            config.get("active_days", DEFAULT_ACTIVE_DAYS),
        )
        await interaction.response.send_message(
            view._status_text(), view=view, ephemeral=True
        )


# Slash commands for rate alert configuration.
class RateCommands(commands.Cog):
    # Store the parent bot instance.
    def __init__(self, bot: "RateHunterBot"):
        self.bot = bot

    # Restrict commands to direct messages.
    async def _ensure_dm(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id is None:
            return True
        await interaction.response.send_message(
            "This command is available in DM only.", ephemeral=True
        )
        return False

    # Load a registered user's config or send an error.
    async def _get_user_config(
        self, interaction: discord.Interaction
    ) -> Optional[Dict[str, Any]]:
        config = await self.bot.config_loader.get_user_by_discord_id(
            str(interaction.user.id)
        )
        if config is not None:
            return config
        if interaction.response.is_done():
            await interaction.followup.send(NOT_REGISTERED_MESSAGE, ephemeral=True)
        else:
            await interaction.response.send_message(
                NOT_REGISTERED_MESSAGE, ephemeral=True
            )
        return None

    @app_commands.command(
        name="register", description="Register yourself to receive CIMB rate alerts"
    )
    # Register a new user with default settings.
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
        config = _default_user_config(name, discord_user_id)
        if await self.bot.config_loader.create_user(discord_user_id, config):
            await interaction.response.send_message(
                _registration_message(name), ephemeral=True
            )
            return
        await interaction.response.send_message(
            "Failed to create your config. Contact the admin.", ephemeral=True
        )

    @app_commands.command(
        name="status", description="Show current rate and your alert config"
    )
    # Show the live rate and current user config.
    async def status(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return
        lines = _status_lines(config, self.bot.snapshot_provider())
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="settarget", description="Set your target SGD->MYR rate")
    # Set the user's target alert rate.
    async def settarget(self, interaction: discord.Interaction, rate: float) -> None:
        if not await self._ensure_dm(interaction):
            return
        if await self._get_user_config(interaction) is None:
            return
        if rate <= 0:
            await interaction.response.send_message(
                "Rate must be greater than 0.", ephemeral=True
            )
            return
        await _send_update_result(
            interaction,
            self.bot.config_loader,
            {"target_rate": round(rate, 4)},
            f"Target updated to {rate:.4f}",
        )

    @app_commands.command(
        name="setwindow", description="Set active alert window (HH:MM HH:MM)"
    )
    # Set the user's active alert window.
    async def setwindow(
        self, interaction: discord.Interaction, start: str, end: str
    ) -> None:
        if not await self._ensure_dm(interaction):
            return
        if await self._get_user_config(interaction) is None:
            return
        if not _is_valid_hhmm(start) or not _is_valid_hhmm(end):
            await interaction.response.send_message(
                "Invalid time. Use HH:MM in 24-hour format.", ephemeral=True
            )
            return
        await _send_update_result(
            interaction,
            self.bot.config_loader,
            {"active_start": start, "active_end": end},
            f"Active window updated to {start} - {end}",
        )

    @app_commands.command(name="toggle", description="Enable or disable your alerts")
    @app_commands.describe(mode="Choose on or off")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    # Enable or disable alerts from a slash command.
    async def toggle(
        self, interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
        if not await self._ensure_dm(interaction):
            return
        if await self._get_user_config(interaction) is None:
            return
        enabled = mode.value == "on"
        await _send_update_result(
            interaction,
            self.bot.config_loader,
            {"enabled": enabled},
            f"Alerts {'enabled' if enabled else 'disabled'}.",
        )

    @app_commands.command(
        name="setdays",
        description="Set which days to receive alerts (e.g. mon tue wed thu fri)",
    )
    # Set which days can send alerts.
    async def setdays(self, interaction: discord.Interaction, days: str) -> None:
        if not await self._ensure_dm(interaction):
            return
        if await self._get_user_config(interaction) is None:
            return
        selected_days, invalid_days = _parse_days(days)
        if not selected_days:
            await interaction.response.send_message(
                "Please provide at least one day.", ephemeral=True
            )
            return
        if invalid_days:
            await interaction.response.send_message(
                f"Invalid days: {', '.join(invalid_days)}. Use: {' '.join(ALL_DAYS)}",
                ephemeral=True,
            )
            return
        await _send_update_result(
            interaction,
            self.bot.config_loader,
            {"active_days": selected_days},
            f"Active days updated to: {', '.join(selected_days)}",
        )

    @app_commands.command(
        name="menu", description="Open your CIMB rate alert settings menu"
    )
    # Open the interactive settings menu.
    async def menu(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_dm(interaction):
            return
        config = await self._get_user_config(interaction)
        if config is None:
            return
        snapshot = self.bot.snapshot_provider()
        embed = _build_menu_embed(config, snapshot)
        view = MenuView(self.bot.config_loader)
        await interaction.response.send_message(
            embed=embed, view=view, ephemeral=True
        )


# Discord bot with slash commands and minimal intents.
class RateHunterBot(commands.Bot):
    # Store dependencies used by slash commands.
    def __init__(
        self,
        config_loader: ConfigLoader,
        snapshot_provider: Callable[[], Dict[str, Any]],
    ):
        super().__init__(command_prefix="!", intents=discord.Intents.none())
        self.config_loader = config_loader
        self.snapshot_provider = snapshot_provider

    # Register slash commands with Discord.
    async def setup_hook(self) -> None:
        load_dotenv()
        await self.add_cog(RateCommands(self))
        synced = await self.tree.sync()
        print(f"[bot] synced {len(synced)} global slash command(s)")
        guild_id = os.getenv("DISCORD_GUILD_ID", "").strip()
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            guild_synced = await self.tree.sync(guild=guild)
            print(f"[bot] synced {len(guild_synced)} guild slash command(s)")

    # Log the bot connection after Discord is ready.
    async def on_ready(self) -> None:
        print(f"[bot] logged in as {self.user} at {datetime.utcnow().isoformat()}Z")


# Create the configured Discord bot instance.
def build_bot(
    config_loader: ConfigLoader,
    snapshot_provider: Callable[[], Dict[str, Any]],
) -> RateHunterBot:
    return RateHunterBot(
        config_loader=config_loader, snapshot_provider=snapshot_provider
    )
