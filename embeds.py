"""Pure builders for the alert DM and the /f panel embeds."""
from __future__ import annotations

from datetime import datetime

import discord

from compare import quotes_for, switch_point, switch_text
from models import Quote, RateState, User
from settings import ALERT_REFERENCE_SGD, TIMEZONE

ALERT_COLOR = discord.Color.from_rgb(226, 75, 74)
PANEL_COLOR = discord.Color.blurple()
NAMES = {"cimb": "CIMB", "wise": "Wise"}
RANKS = ("1.", "2.")


def format_myr(amount: float) -> str:
    return f"RM {amount:,.2f}"


def format_age(then: datetime | None, now: datetime) -> str:
    if then is None:
        return "no data yet"
    minutes = int((now - then).total_seconds() // 60)
    if minutes < 1:
        return "updated just now"
    if minutes < 60:
        return f"updated {minutes} min ago"
    return f"updated {minutes // 60} h ago"


def _switch_line(state: RateState) -> str | None:
    if state.cimb_rate is None or state.wise_rate is None:
        return None
    return switch_text(switch_point(state.cimb_rate, state.wise_rate, state.wise_fee))


def _quote_line(index: int, quote: Quote) -> str:
    rank = RANKS[index] if index < len(RANKS) else f"{index + 1}."
    line = f"{rank} {NAMES[quote.provider]}   {format_myr(quote.received_myr)}"
    if quote.fee_sgd:
        line += f"   fee SGD {quote.fee_sgd:.2f}"
    return line


def alert_preview_text(state: RateState) -> str:
    quotes = quotes_for(state, ALERT_REFERENCE_SGD)
    if not quotes:
        return "SGD → MYR: no rate"
    best = quotes[0]
    return f"SGD → MYR: {best.effective_rate:.4f} ({NAMES[best.provider]})"


def build_alert_embed(user: User, state: RateState, amount_sgd: float, now: datetime) -> discord.Embed:
    reference = quotes_for(state, ALERT_REFERENCE_SGD)
    if reference:
        best = reference[0]
        title = f"Target hit: {best.effective_rate:.4f} effective ({NAMES[best.provider]})"
    else:
        title = "SGD → MYR"
    parts = []
    if state.wise_rate is not None:
        parts.append(f"Mid-market {state.wise_rate:.4f}")
    parts.append(f"your target {user.target_rate:.4f}")
    description = " · ".join(parts)
    description = description[0].upper() + description[1:]

    quotes = quotes_for(state, amount_sgd)
    if quotes:
        lines = [_quote_line(i, q) for i, q in enumerate(quotes)]
        switch = _switch_line(state)
        if switch:
            lines += ["", f"Best by amount: {switch}"]
        body = "\n".join(lines)
    else:
        body = "No rates right now."

    embed = discord.Embed(title=title, description=description, color=ALERT_COLOR, timestamp=now)
    embed.add_field(name=f"For SGD {amount_sgd:,.0f}:", value=body, inline=False)
    return embed


def build_panel_embed(user: User, state: RateState, amount_sgd: float, now: datetime) -> discord.Embed:
    stamps = [t for t in (state.cimb_at, state.wise_at) if t is not None]
    title = f"SGD → MYR · {format_age(max(stamps) if stamps else None, now)}"

    rates = []
    if state.cimb_rate is not None:
        rates.append(f"CIMB {state.cimb_rate:.4f}")
    if state.wise_rate is not None:
        fee = state.wise_fee
        rates.append(f"Wise {state.wise_rate:.4f} (fee {fee.fixed_sgd:.2f} + {fee.pct * 100:.2f}%)")
    lines = [" · ".join(rates) if rates else "No rates yet — rates update Mon–Fri, 9am–8pm."]

    switch = _switch_line(state)
    if switch:
        lines.append(f"Best by amount: {switch}")
    alerts = "On" if user.enabled else "Off"
    lines.append(f"Your target {user.target_rate:.4f} · Alerts: {alerts}")
    if user.snoozed_until:
        until = datetime.fromisoformat(user.snoozed_until)
        if until > now:
            lines.append(f"Snoozed until {until.astimezone(TIMEZONE):%H:%M}")

    quotes = quotes_for(state, amount_sgd)
    if quotes:
        ranked = " · ".join(f"{NAMES[q.provider]} {format_myr(q.received_myr)}" for q in quotes)
        lines += ["", f"For SGD {amount_sgd:,.0f}:  {ranked}"]

    return discord.Embed(title=title, description="\n".join(lines), color=PANEL_COLOR)


HELP_COMMANDS = (
    ("/f", "Your panel: live CIMB & Wise rates, which is cheaper for your amount, target, alerts on/off, compare any amount."),
    ("/t rate", "Set your target rate after fees, e.g. `/t 3.1650`. You're alerted when CIMB or Wise reaches it."),
    ("/a on|off", "Turn alerts on or off."),
    ("/reg name", "Register (once) before using the other commands."),
    ("/help", "Show this list."),
)


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="SGD → MYR bot · commands",
        description="Use these in a DM with me.",
        color=PANEL_COLOR,
    )
    for name, text in HELP_COMMANDS:
        embed.add_field(name=name, value=text, inline=False)
    embed.add_field(
        name="Alerts",
        value=(
            "Checked every minute, Mon–Fri 9am–8pm (Singapore). "
            "Each alert has a **Compare** dropdown (200 / 500 / 1,000 / 2,000 / 3,000 / Other), "
            "**Open Wise**, and **Snooze 1h**."
        ),
        inline=False,
    )
    return embed
