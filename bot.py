"""Discord bot: /reg, /t, /a, /f (DM only) and command sync."""
from __future__ import annotations

import hashlib
import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

from chart_service import ChartMaker
from db import Database
from models import RateState
from settings import ALERT_REFERENCE_SGD, DEFAULT_TARGET, Secrets
from embeds import build_help_embed
from ui import NOT_REGISTERED, AlertView, show_panel

log = logging.getLogger(__name__)

COMMAND_NAMES = ("reg", "t", "a", "f", "help")
DM_ONLY = "This bot only works in DMs. Message me directly."


def commands_hash(tree: app_commands.CommandTree) -> str:
    signature = sorted(
        (cmd.name, cmd.description, [p.name for p in getattr(cmd, "parameters", [])])
        for cmd in tree.get_commands()
    )
    return hashlib.sha256(json.dumps(signature).encode()).hexdigest()


class RateCommands(commands.Cog):
    def __init__(self, bot: "RateBot"):
        self.bot = bot

    async def _ensure_dm(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id is None:
            return True
        await interaction.response.send_message(DM_ONLY, ephemeral=True)
        return False

    async def _registered(self, interaction: discord.Interaction) -> bool:
        if self.bot.db.get_user(str(interaction.user.id)) is not None:
            return True
        await interaction.response.send_message(NOT_REGISTERED, ephemeral=True)
        return False

    @app_commands.command(name="reg", description="Register for SGD→MYR rate alerts")
    @app_commands.describe(name="Your display name")
    async def reg(self, interaction: discord.Interaction, name: str) -> None:
        if not await self._ensure_dm(interaction):
            return
        uid = str(interaction.user.id)
        existing = self.bot.db.get_user(uid)
        if existing is not None:
            await interaction.response.send_message(
                f"You're already registered as **{existing.name}**. Use /f.", ephemeral=True
            )
            return
        self.bot.db.create_user(uid, name)
        await interaction.response.send_message(
            f"Registered as **{name}**! Default target {DEFAULT_TARGET:.4f}. "
            "Use /f to see live rates and change settings, or /help for all commands.",
            ephemeral=True,
        )

    @app_commands.command(name="t", description="Set your target SGD→MYR rate (after fees)")
    @app_commands.describe(rate="e.g. 3.1650")
    async def t(self, interaction: discord.Interaction, rate: float) -> None:
        if not await self._ensure_dm(interaction) or not await self._registered(interaction):
            return
        if rate <= 0:
            await interaction.response.send_message("Rate must be greater than 0.", ephemeral=True)
            return
        self.bot.db.update_user(str(interaction.user.id), target_rate=round(rate, 4))
        await interaction.response.send_message(f"Target set to {rate:.4f}.", ephemeral=True)

    @app_commands.command(name="a", description="Turn your alerts on or off")
    @app_commands.choices(
        mode=[app_commands.Choice(name="on", value="on"), app_commands.Choice(name="off", value="off")]
    )
    async def a(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        if not await self._ensure_dm(interaction) or not await self._registered(interaction):
            return
        enabled = mode.value == "on"
        self.bot.db.update_user(str(interaction.user.id), enabled=enabled)
        await interaction.response.send_message(
            "🔔 Alerts on." if enabled else "🔕 Alerts off.", ephemeral=True
        )

    @app_commands.command(name="f", description="Open your rates and settings panel")
    async def f(self, interaction: discord.Interaction) -> None:
        if not await self._ensure_dm(interaction):
            return
        await show_panel(
            interaction,
            self.bot.db,
            self.bot.state,
            str(interaction.user.id),
            ALERT_REFERENCE_SGD,
            self.bot.chart_maker,
            edit=False,
        )

    @app_commands.command(name="help", description="Show what each command does")
    async def help(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=build_help_embed(), ephemeral=True)


async def register_commands(bot: "RateBot") -> None:
    await bot.add_cog(RateCommands(bot))


async def sync_commands(bot: "RateBot") -> None:
    """Sync slash commands only when they changed. Failures never stop startup."""
    digest = commands_hash(bot.tree)
    if bot.db.get_meta("commands_hash") != digest:
        try:
            await bot.tree.sync()
        except discord.DiscordException as exc:
            log.error("command sync failed (will retry next start): %r", exc)
        else:
            bot.db.set_meta("commands_hash", digest)


class RateBot(commands.Bot):
    def __init__(self, db: Database, state: RateState, secrets: Secrets, chart_maker: ChartMaker | None = None):
        super().__init__(command_prefix="!", intents=discord.Intents.none())
        self.db, self.state, self.secrets = db, state, secrets
        self.chart_maker = chart_maker

    async def setup_hook(self) -> None:
        self.add_view(AlertView(self.db, self.state))
        await register_commands(self)
        await sync_commands(self)

    async def on_app_command_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.error("command %s failed: %r", getattr(interaction.command, "name", "?"), error)


def build_bot(
    db: Database, state: RateState, secrets: Secrets, chart_maker: ChartMaker | None = None
) -> RateBot:
    bot = RateBot(db, state, secrets, chart_maker)
    bot.tree.on_error = bot.on_app_command_error
    return bot
