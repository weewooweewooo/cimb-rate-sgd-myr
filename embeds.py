"""Pure builders for the alert DM, the /f panel and /help embeds.

Plain text only (no emoji). Status is shown by the embed's side-bar colour,
headings (`##`), small grey text (`-#`), monospace tables and Discord's
live timestamps (`<t:unix:R>`, e.g. "2 minutes ago", in the viewer's time).
"""
from __future__ import annotations

from datetime import datetime

import discord

from compare import quotes_for, switch_point, switch_text
from models import Quote, RateState, User
from settings import ALERT_REFERENCE_SGD, REALERT_STEP

GREEN = discord.Color.from_rgb(35, 165, 90)  # at or above target
AMBER = discord.Color.from_rgb(240, 178, 50)  # within REALERT_STEP below target
GREY = discord.Color.from_rgb(128, 132, 142)  # below target
NO_DATA = discord.Color.blurple()  # no rates (weekend / outside hours / both providers down)
NAMES = {"cimb": "CIMB", "wise": "Wise"}
NO_RATES_PANEL = "No rates yet — rates update Mon–Fri, 9am–8pm."

Changes = dict[str, float]


def format_myr(amount: float) -> str:
    return f"RM {amount:,.2f}"


def live_time(moment: datetime) -> str:
    """Discord renders this as relative time ("2 minutes ago") and keeps it ticking."""
    return f"<t:{int(moment.timestamp())}:R>"


def change_text(delta: float | None) -> str:
    if delta is None:
        return ""
    if abs(delta) < 0.00005:
        return "unchanged"
    return f"▲ +{delta:.4f}" if delta > 0 else f"▼ -{abs(delta):.4f}"


def status_color(best: float | None, target: float) -> discord.Color:
    if best is None:
        return NO_DATA
    if best >= target:
        return GREEN
    if best >= target - REALERT_STEP:
        return AMBER
    return GREY


def _best(state: RateState) -> Quote | None:
    reference = quotes_for(state, ALERT_REFERENCE_SGD)
    return reference[0] if reference else None


def _switch_line(state: RateState) -> str | None:
    if state.cimb_rate is None or state.wise_rate is None:
        return None
    return "**Best by amount:** " + switch_text(switch_point(state.cimb_rate, state.wise_rate, state.wise_fee))


def _ranking_block(quotes: list[Quote]) -> str:
    rows = []
    for index, quote in enumerate(quotes, start=1):
        row = f"{index}. {NAMES[quote.provider]:<4}  {format_myr(quote.received_myr):>12}"
        if quote.fee_sgd:
            row += f"  fee {quote.fee_sgd:.2f}"
        rows.append(row)
    return "```\n" + "\n".join(rows) + "\n```"


def _fee_note(state: RateState) -> str:
    fee = state.wise_fee
    return f"-# Wise fee SGD {fee.fixed_sgd:.2f} + {fee.pct * 100:.2f}% (cheapest PayNow / bank pay-in)"


def alert_preview_text(state: RateState, target: float) -> str:
    best = _best(state)
    if best is None:
        return "SGD → MYR: no rate"
    return f"SGD → MYR: {best.effective_rate:.4f} ({NAMES[best.provider]}) · target {target:.4f}"


def build_alert_embed(
    user: User, state: RateState, amount_sgd: float, now: datetime, changes: Changes | None = None
) -> discord.Embed:
    changes = changes or {}
    best = _best(state)
    if best is None:
        description = f"-# SGD → MYR\nNo rates right now.\n-# Updated {live_time(now)}"
        return discord.Embed(description=description, color=NO_DATA)

    heading = f"## {best.effective_rate:.4f}"
    best_change = change_text(changes.get(best.provider))
    if best_change:
        heading += f" {best_change} today"
    context = []
    if state.wise_rate is not None:
        context.append(" ".join(filter(None, [f"Mid-market {state.wise_rate:.4f}", change_text(changes.get("wise"))])))
    context.append(f"your target {user.target_rate:.4f}")
    context_line = " · ".join(context)
    lines = [
        f"-# TARGET HIT · {NAMES[best.provider]}",
        heading,
        context_line[0].upper() + context_line[1:],
        f"-# Updated {live_time(now)}",
    ]
    embed = discord.Embed(description="\n".join(lines), color=status_color(best.effective_rate, user.target_rate))

    body = [_ranking_block(quotes_for(state, amount_sgd))]
    switch = _switch_line(state)
    if switch:
        body.append(switch)
    if state.wise_rate is not None:
        body.append(_fee_note(state))
    embed.add_field(name=f"For SGD {amount_sgd:,.0f}", value="\n".join(body), inline=False)
    return embed


def _rate_rows(state: RateState, changes: Changes) -> list[str]:
    rows = []

    def row(name: str, rate: float, change: str, note: str = "") -> str:
        return f"{name:<4}  {rate:.4f}  {change:<9}  {note}".rstrip()

    if state.cimb_rate is not None:
        rows.append(row("CIMB", state.cimb_rate, change_text(changes.get("cimb"))))
    if state.wise_rate is not None:
        rows.append(row("Wise", state.wise_rate, change_text(changes.get("wise")), "before fee"))
        net = state.wise_rate * (1 - state.wise_fee.fee_for(ALERT_REFERENCE_SGD) / ALERT_REFERENCE_SGD)
        rows.append(row("", net, "", f"after fee, SGD {ALERT_REFERENCE_SGD:,.0f}"))
    return rows


def build_panel_embed(
    user: User, state: RateState, amount_sgd: float, now: datetime, changes: Changes | None = None
) -> discord.Embed:
    changes = changes or {}
    stamps = [t for t in (state.cimb_at, state.wise_at) if t is not None]
    header = f"-# SGD → MYR · updated {live_time(max(stamps))}" if stamps else "-# SGD → MYR · no data yet"
    lines = [header]
    rows = _rate_rows(state, changes)
    if rows:
        lines += ["```", *rows, "```"]
    else:
        lines.append(NO_RATES_PANEL)
    switch = _switch_line(state)
    if switch:
        lines.append(switch)
    lines.append(f"Your target **{user.target_rate:.4f}** · Alerts: **{'On' if user.enabled else 'Off'}**")

    best = _best(state)
    embed = discord.Embed(
        description="\n".join(lines),
        color=status_color(best.effective_rate if best else None, user.target_rate),
    )
    quotes = quotes_for(state, amount_sgd)
    if quotes:
        embed.add_field(name=f"For SGD {amount_sgd:,.0f}", value=_ranking_block(quotes), inline=False)
    return embed


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
        color=NO_DATA,
    )
    for name, text in HELP_COMMANDS:
        embed.add_field(name=name, value=text, inline=False)
    embed.add_field(
        name="Alerts",
        value=(
            "Checked every minute, Mon–Fri 9am–8pm (Singapore). You get a DM when CIMB or Wise reaches your "
            "target, and again each time it climbs another 0.0010. Each alert has a **Compare** dropdown "
            "(200 / 500 / 1,000 / 2,000 / 3,000 / Other) to re-rank it for any amount."
        ),
        inline=False,
    )
    return embed
