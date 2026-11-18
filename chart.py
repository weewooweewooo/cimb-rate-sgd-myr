"""Rate history chart with an honest 'likely next 24 h' band (not a forecast)."""
from __future__ import annotations

import bisect
import io
import statistics
from datetime import datetime, timedelta

Series = list[tuple[datetime, float]]


def date_formatter():
    import matplotlib.dates as mdates

    from settings import TIMEZONE

    return mdates.DateFormatter("%d %b", tz=TIMEZONE)


def likely_band(history: Series, current: float) -> tuple[float, float]:
    """10th-90th percentile of past 24 h relative moves, applied to `current`."""
    times = [t for t, _ in history]
    changes: list[float] = []
    for i, (start, value) in enumerate(history):
        j = bisect.bisect_left(times, start + timedelta(hours=24), lo=i + 1)
        if j < len(history):
            changes.append(history[j][1] / value - 1)
    if len(changes) < 10:
        return (current, current)
    deciles = statistics.quantiles(changes, n=10)
    return (current * (1 + deciles[0]), current * (1 + deciles[-1]))


def percentile_rank(history: Series, value: float) -> int:
    if not history:
        return 0
    below = sum(1 for _, v in history if v < value)
    return round(100 * below / len(history))


def series_labels(mid: Series, wise_net: Series, cimb: Series, target: float) -> dict[str, str]:
    """Legend labels carrying each line's latest conversion rate."""
    labels: dict[str, str] = {}
    if mid:
        labels["mid"] = f"Wise mid-market (before fee)  {mid[-1][1]:.4f}"
    if wise_net:
        labels["net"] = f"Wise after fees, SGD 1,000  {wise_net[-1][1]:.4f}"
    if cimb:
        labels["cimb"] = f"CIMB  {cimb[-1][1]:.4f}"
    labels["target"] = f"Your target  {target:.4f}"
    return labels


def caption(mid_rate: float, pct_rank: int) -> str:
    return (
        f"Mid-market {mid_rate:.4f} is higher than {pct_rank}% of the last 30 days"
        " · shaded = likely range next 24 h, not a forecast"
    )


def render_chart(
    mid: Series,
    cimb: Series,
    target: float,
    current: float,
    band: tuple[float, float],
    pct_rank: int,
    wise_net: Series | None = None,
) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4), dpi=110)
    try:
        wise_net = wise_net or []
        labels = series_labels(mid, wise_net, cimb, target)
        lines = (
            ("mid", mid, "#4c6ef5", "-"),
            ("net", wise_net, "#4c6ef5", ":"),
            ("cimb", cimb, "#e24b4a", "-"),
        )
        for key, series, color, style in lines:
            if not series:
                continue
            xs, ys = [t for t, _ in series], [v for _, v in series]
            if key == "cimb":
                ax.step(xs, ys, where="post", color=color, lw=1.6, label=labels[key])
            else:
                ax.plot(xs, ys, color=color, ls=style, lw=1.6, label=labels[key])
            ax.annotate(
                f"{ys[-1]:.4f}", xy=(xs[-1], ys[-1]), xytext=(-6, 6 if key != "net" else -12),
                textcoords="offset points", ha="right", fontsize=8, color=color, fontweight="bold",
            )
        ax.axhline(target, color="#2b8a3e", ls="--", lw=1.2, label=labels["target"])
        stamps = [t for t, _ in mid] + [t for t, _ in cimb]
        if stamps:
            now = max(stamps)
            ax.fill_between([now, now + timedelta(hours=24)], band[0], band[1], color="#4c6ef5", alpha=0.15)
            ax.plot([now], [current], "o", color="#4c6ef5")
        ax.xaxis.set_major_formatter(date_formatter())
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", fontsize=8, frameon=True, framealpha=0.85)
        ax.set_title(caption(current, pct_rank), fontsize=8.5)
        fig.tight_layout()
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png")
        return buffer.getvalue()
    finally:
        plt.close(fig)
