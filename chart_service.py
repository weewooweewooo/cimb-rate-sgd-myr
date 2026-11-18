"""Build the rate chart attachment for alerts and the /f panel.

Wise's 30-day history is cached for a few minutes so panel button taps
do not re-download it every time.
"""
from __future__ import annotations

import asyncio
import io
import logging
import time
from datetime import datetime, timedelta
from typing import Awaitable, Callable

import discord

from chart import likely_band, percentile_rank, render_chart
from db import Database
from models import RateState, WiseFee
from settings import ALERT_REFERENCE_SGD

log = logging.getLogger(__name__)

Series = list[tuple[datetime, float]]
HistoryFetcher = Callable[[], Awaitable[Series]]
CHART_DAYS = 7
HISTORY_CACHE_SECONDS = 600
CHART_FILENAME = "chart.png"


def wise_net_series(mid: Series, fee: WiseFee, amount_sgd: float) -> Series:
    """Wise rate after its fee, i.e. MYR received per SGD sent at `amount_sgd`."""
    keep = (amount_sgd - fee.fee_for(amount_sgd)) / amount_sgd
    return [(t, v * keep) for t, v in mid]


class ChartMaker:
    def __init__(
        self,
        history_fetcher: HistoryFetcher,
        db: Database,
        ttl_seconds: float = HISTORY_CACHE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._fetch, self._db = history_fetcher, db
        self._ttl, self._clock = ttl_seconds, clock
        self._history: Series | None = None
        self._fetched_at = 0.0

    async def _get_history(self) -> Series:
        if self._history is None or self._clock() - self._fetched_at >= self._ttl:
            self._history = await self._fetch()
            self._fetched_at = self._clock()
        return self._history

    async def make(self, target: float, state: RateState, now: datetime) -> discord.File | None:
        """PNG chart as a Discord attachment, or None if it can't be drawn right now."""
        if state.wise_rate is None:
            return None
        try:
            history = await self._get_history()
            since = now - timedelta(days=CHART_DAYS)
            mid = [point for point in history if point[0] >= since]
            cimb = self._db.rates_since("cimb", since)
            net = wise_net_series(mid, state.wise_fee, ALERT_REFERENCE_SGD)
            band = likely_band(history, state.wise_rate)
            rank = percentile_rank(history, state.wise_rate)
            png = await asyncio.to_thread(render_chart, mid, cimb, target, state.wise_rate, band, rank, net)
        except Exception as exc:
            log.error("chart skipped: %r", exc)
            return None
        return discord.File(io.BytesIO(png), filename=CHART_FILENAME)
