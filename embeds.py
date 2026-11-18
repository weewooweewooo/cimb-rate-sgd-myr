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
MEDALS = ("🥇", "🥈")


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
    medal = MEDALS[index] if index < len(MEDALS) else "  "
    line = f"{medal} {NAMES[quote.provider]}   {format_myr(quote.received_myr)}"
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
        title = f"💱 Target hit: {best.effective_rate:.4f} effective ({NAMES[best.provider]})"
    else:
        title = "💱 SGD → MYR"
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
            lines += ["", f"💡 {switch}"]
        body = "\n".join(lines)
    else:
        body = "No rates right now."

    embed = discord.Embed(title=title, description=description, color=ALERT_COLOR, timestamp=now)
    embed.add_field(name=f"For SGD {amount_sgd:,.0f}:", value=body, inline=False)
    return embed


def build_panel_embed(user: User, state: RateState, amount_sgd: float, now: datetime) -> discord.Embed:
    stamps = [t for t in (state.cimb_at, state.wise_at) if t is not None]
    title = f"⚙️ SGD → MYR · {format_age(max(stamps) if stamps else None, now)}"

    rates = []
    if state.cimb_rate is not None:
        rates.append(f"CIMB {state.cimb_rate:.4f}")
    if state.wise_rate is not None:
        fee = state.wise_fee
        rates.append(f"Wise {state.wise_rate:.4f} (fee {fee.fixed_sgd:.2f} + {fee.pct * 100:.2f}%)")
    lines = [" · ".join(rates) if rates else "No rates yet — rates update Mon–Fri, 9am–8pm."]

    switch = _switch_line(state)
    if switch:
        lines.append(f"💡 {switch}")
    alerts = "🔔 On" if user.enabled else "🔕 Off"
    lines.append(f"Your target {user.target_rate:.4f} · Alerts {alerts}")
    if user.snoozed_until:
        until = datetime.fromisoformat(user.snoozed_until)
        if until > now:
            lines.append(f"😴 Snoozed until {until.astimezone(TIMEZONE):%H:%M}")

    quotes = quotes_for(state, amount_sgd)
    if quotes:
        ranked = " · ".join(f"{NAMES[q.provider]} {format_myr(q.received_myr)}" for q in quotes)
        lines += ["", f"For SGD {amount_sgd:,.0f}:  {ranked}"]

    return discord.Embed(title=title, description="\n".join(lines), color=PANEL_COLOR)
