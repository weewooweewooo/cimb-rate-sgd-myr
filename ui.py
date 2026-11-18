"""Discord views and modals: compare dropdown, alert buttons, /f panel."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Awaitable, Callable

import discord

from compare import parse_amount
from db import Database
from embeds import build_alert_embed, build_panel_embed
from models import RateState, User
from settings import COMPARE_PRESETS, SNOOZE_MINUTES, TIMEZONE, WISE_SEND_URL

if TYPE_CHECKING:
    from chart_service import ChartMaker

CHART_FILENAME = "chart.png"

log = logging.getLogger(__name__)

Render = Callable[[discord.Interaction, float], Awaitable[None]]

NOT_REGISTERED = "You are not registered yet. Use /reg first."
BAD_AMOUNT = "Enter an amount between SGD 10 and SGD 100,000, e.g. 1,523."
BAD_TARGET = "Target must be a number greater than 0, e.g. 3.1650."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def keep_chart(embed: discord.Embed, message: object) -> None:
    """Keep an alert's chart visible when its embed is rebuilt (e.g. by Compare)."""
    attachments = getattr(message, "attachments", None) or []
    if any(getattr(a, "filename", None) == CHART_FILENAME for a in attachments):
        embed.set_image(url=f"attachment://{CHART_FILENAME}")


def _is_snoozed(user: User, now: datetime) -> bool:
    return bool(user.snoozed_until) and datetime.fromisoformat(user.snoozed_until) > now


class AmountModal(discord.ui.Modal, title="Compare amount"):
    amount = discord.ui.TextInput(label="Amount in SGD", placeholder="e.g. 1,523", max_length=20)

    def __init__(self, render: Render):
        super().__init__()
        self._render = render

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = parse_amount(str(self.amount.value))
        if value is None:
            await interaction.response.send_message(BAD_AMOUNT, ephemeral=True)
            return
        await self._render(interaction, value)


class CompareSelect(discord.ui.Select):
    def __init__(self, render: Render | None, custom_id: str | None, selected: float):
        options = [
            discord.SelectOption(label=f"SGD {amount:,}", value=str(amount), default=amount == selected)
            for amount in COMPARE_PRESETS
        ]
        options.append(discord.SelectOption(label="Other…", value="other"))
        kwargs = {"custom_id": custom_id} if custom_id else {}
        super().__init__(placeholder=f"Compare: SGD {selected:,.0f}", options=options, **kwargs)
        self._render = render

    async def callback(self, interaction: discord.Interaction) -> None:
        choice = self.values[0]
        if choice == "other":
            await interaction.response.send_modal(AmountModal(self._render))
            return
        await self._render(interaction, float(choice))


class AlertView(discord.ui.View):
    """Buttons on alert DMs. Persistent: registered once at startup."""

    def __init__(self, db: Database, state: RateState, selected: float = 1000.0):
        super().__init__(timeout=None)
        self.db, self.state = db, state
        self.add_item(CompareSelect(self._render, "alert:compare", selected))
        self.add_item(discord.ui.Button(label="Open Wise", url=WISE_SEND_URL))
        snooze = discord.ui.Button(label=f"Snooze {SNOOZE_MINUTES // 60}h", custom_id="alert:snooze")
        snooze.callback = self._snooze
        self.add_item(snooze)

    async def _render(self, interaction: discord.Interaction, amount: float) -> None:
        user = self.db.get_user(str(interaction.user.id))
        if user is None:
            await interaction.response.send_message(NOT_REGISTERED, ephemeral=True)
            return
        embed = build_alert_embed(user, self.state, amount, _now())
        keep_chart(embed, interaction.message)
        await interaction.response.edit_message(embed=embed, view=AlertView(self.db, self.state, amount))

    async def _snooze(self, interaction: discord.Interaction) -> None:
        until = _now() + timedelta(minutes=SNOOZE_MINUTES)
        if not self.db.update_user(str(interaction.user.id), snoozed_until=until.isoformat()):
            await interaction.response.send_message(NOT_REGISTERED, ephemeral=True)
            return
        await interaction.response.send_message(
            f"Snoozed until {until.astimezone(TIMEZONE):%H:%M}.", ephemeral=True
        )


async def show_panel(
    interaction: discord.Interaction,
    db: Database,
    state: RateState,
    user_id: str,
    amount: float,
    chart_maker: ChartMaker | None = None,
    *,
    edit: bool,
) -> None:
    user = db.get_user(user_id)
    if user is None:
        await interaction.response.send_message(NOT_REGISTERED, ephemeral=True)
        return
    # Acknowledge within Discord's 3 s limit; the chart is drawn afterwards.
    if edit:
        await interaction.response.defer()
    else:
        await interaction.response.defer(ephemeral=True, thinking=True)
    now = _now()
    embed = build_panel_embed(user, state, amount, now)
    chart = await chart_maker.make(user.target_rate, state, now) if chart_maker else None
    files = [chart] if chart is not None else []
    if chart is not None:
        embed.set_image(url=f"attachment://{CHART_FILENAME}")
    view = PanelView(db, state, user_id, amount, chart_maker)
    if edit:
        await interaction.edit_original_response(embed=embed, view=view, attachments=files)
    else:
        await interaction.followup.send(embed=embed, view=view, files=files, ephemeral=True)


class TargetModal(discord.ui.Modal, title="Set target rate"):
    rate = discord.ui.TextInput(label="Target SGD→MYR rate (after fees)", placeholder="e.g. 3.1650", max_length=10)

    def __init__(
        self, db: Database, state: RateState, user_id: str, amount: float, chart_maker: ChartMaker | None = None
    ):
        super().__init__()
        self.db, self.state, self.user_id, self.amount = db, state, user_id, amount
        self.chart_maker = chart_maker

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            value = float(str(self.rate.value).strip())
        except ValueError:
            value = 0.0
        if not value > 0:
            await interaction.response.send_message(BAD_TARGET, ephemeral=True)
            return
        self.db.update_user(self.user_id, target_rate=round(value, 4))
        await show_panel(interaction, self.db, self.state, self.user_id, self.amount, self.chart_maker, edit=True)


class PanelView(discord.ui.View):
    """The /f panel. Every action re-renders this same message."""

    def __init__(
        self, db: Database, state: RateState, user_id: str, amount: float, chart_maker: ChartMaker | None = None
    ):
        super().__init__(timeout=600)
        self.db, self.state, self.user_id, self.amount = db, state, user_id, amount
        self.chart_maker = chart_maker
        user = db.get_user(user_id)
        enabled = bool(user and user.enabled)

        self._button("Target", discord.ButtonStyle.primary, self._target)
        self._button(
            "Alerts: On" if enabled else "Alerts: Off",
            discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary,
            self._toggle,
        )
        self._button("Refresh", discord.ButtonStyle.secondary, self._refresh)
        if user and _is_snoozed(user, _now()):
            self._button("Unsnooze", discord.ButtonStyle.secondary, self._unsnooze)
        self.add_item(CompareSelect(self._compare, None, amount))

    def _button(self, label: str, style: discord.ButtonStyle, callback) -> None:
        button = discord.ui.Button(label=label, style=style, row=0)
        button.callback = callback
        self.add_item(button)

    async def _rerender(self, interaction: discord.Interaction, amount: float | None = None) -> None:
        await show_panel(
            interaction, self.db, self.state, self.user_id, amount or self.amount, self.chart_maker, edit=True
        )

    async def _target(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            TargetModal(self.db, self.state, self.user_id, self.amount, self.chart_maker)
        )

    async def _toggle(self, interaction: discord.Interaction) -> None:
        user = self.db.get_user(self.user_id)
        if user is not None:
            self.db.update_user(self.user_id, enabled=not user.enabled)
        await self._rerender(interaction)

    async def _refresh(self, interaction: discord.Interaction) -> None:
        await self._rerender(interaction)

    async def _unsnooze(self, interaction: discord.Interaction) -> None:
        self.db.update_user(self.user_id, snoozed_until=None)
        await self._rerender(interaction)

    async def _compare(self, interaction: discord.Interaction, amount: float) -> None:
        await self._rerender(interaction, amount)
