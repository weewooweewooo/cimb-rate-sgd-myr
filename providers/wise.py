"""Wise SGD->MYR: live mid-market rate and fee (cheapest bank/PayNow pay-in)."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from models import WiseFee
from providers import ProviderError
from settings import WISE_ALLOWED_PAYINS, WISE_LIVE_URL, WISE_PRICE_URL


def parse_wise_live(payload: object) -> float:
    value = payload.get("value") if isinstance(payload, dict) else None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ProviderError("Wise live rate missing")
    return float(value)


def parse_wise_fee(entries: object, amount_sgd: float) -> WiseFee:
    if not isinstance(entries, list):
        raise ProviderError("Wise price response is not a list")
    best: dict[str, Any] | None = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("payOutMethod") != "BANK_TRANSFER" or entry.get("payInMethod") not in WISE_ALLOWED_PAYINS:
            continue
        if not all(isinstance(entry.get(k), (int, float)) for k in ("total", "variableFeePercent")):
            continue
        if best is None or entry["total"] < best["total"]:
            best = entry
    if best is None:
        raise ProviderError("no bank/PayNow pay-in found in Wise price response")
    pct = float(best["variableFeePercent"]) / 100
    fixed = round(float(best["total"]) - pct * amount_sgd, 4)
    return WiseFee(fixed_sgd=fixed, pct=pct)


async def _get_json(session: aiohttp.ClientSession, url: str, params: dict[str, str]) -> object:
    try:
        async with session.get(url, params=params) as response:
            if response.status != 200:
                raise ProviderError(f"Wise HTTP {response.status}")
            return await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        raise ProviderError(f"Wise request failed: {exc!r}") from exc


async def fetch_wise_live(session: aiohttp.ClientSession) -> float:
    payload = await _get_json(session, WISE_LIVE_URL, {"source": "SGD", "target": "MYR"})
    return parse_wise_live(payload)


async def fetch_wise_fee(session: aiohttp.ClientSession, amount_sgd: float) -> WiseFee:
    params = {"sourceAmount": f"{amount_sgd:.0f}", "sourceCurrency": "SGD", "targetCurrency": "MYR"}
    payload = await _get_json(session, WISE_PRICE_URL, params)
    return parse_wise_fee(payload, amount_sgd)
