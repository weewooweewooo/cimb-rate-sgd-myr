"""Rate history chart with an honest 'likely next 24 h' band (not a forecast)."""
from __future__ import annotations

import bisect
import io
import statistics
from datetime import datetime, timedelta

Series = list[tuple[datetime, float]]


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


def caption(mid_rate: float, pct_rank: int) -> str:
    return (
        f"Mid-market {mid_rate:.4f} is higher than {pct_rank}% of the last 30 days"
        " · shaded = likely range next 24 h, not a forecast"
    )


def render_chart(
    mid: Series, cimb: Series, target: float, current: float, band: tuple[float, float], pct_rank: int
) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4), dpi=110)
    try:
        if mid:
            ax.plot([t for t, _ in mid], [v for _, v in mid], color="#4c6ef5", lw=1.6, label="Mid-market (Wise)")
        if cimb:
            ax.step([t for t, _ in cimb], [v for _, v in cimb], where="post", color="#e24b4a", lw=1.6, label="CIMB")
        ax.axhline(target, color="#2b8a3e", ls="--", lw=1.2, label=f"Your target {target:.4f}")
        stamps = [t for t, _ in mid] + [t for t, _ in cimb]
        if stamps:
            now = max(stamps)
            ax.fill_between([now, now + timedelta(hours=24)], band[0], band[1], color="#4c6ef5", alpha=0.15)
            ax.plot([now], [current], "o", color="#4c6ef5")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", fontsize=8, frameon=False)
        ax.set_title(caption(current, pct_rank), fontsize=8.5)
        fig.tight_layout()
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png")
        return buffer.getvalue()
    finally:
        plt.close(fig)
