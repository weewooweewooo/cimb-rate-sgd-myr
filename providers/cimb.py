"""CIMB SGD->MYR rate, read from the public page's hidden rateList input."""
from __future__ import annotations

import asyncio
import re

import aiohttp

from providers import ProviderError
from settings import CIMB_RATE_URL

_INPUT_TAG = re.compile(r"<input\b[^>]*rateList[^>]*>", re.IGNORECASE)
_VALUE = re.compile(r'value="\[\s*([0-9]+(?:\.[0-9]+)?)')


def parse_cimb_rate(html: str) -> float:
    for tag in _INPUT_TAG.findall(html):
        match = _VALUE.search(tag)
        if match:
            rate = float(match.group(1))
            if rate > 0:
                return rate
    raise ProviderError("CIMB rateList value not found")


async def fetch_cimb_rate(session: aiohttp.ClientSession) -> float:
    try:
        async with session.get(CIMB_RATE_URL) as response:
            if response.status != 200:
                raise ProviderError(f"CIMB HTTP {response.status}")
            html = await response.text()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise ProviderError(f"CIMB request failed: {exc!r}") from exc
    return parse_cimb_rate(html)
