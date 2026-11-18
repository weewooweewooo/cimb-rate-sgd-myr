"""CIMB vs Wise money maths: quotes, ranking, switch point, amount parsing."""
from __future__ import annotations

import math
import re

from models import Quote, RateState, SwitchPoint, WiseFee
from settings import AMOUNT_MAX_SGD, AMOUNT_MIN_SGD

_AMOUNT_PREFIX = re.compile(r"^(sgd|s\$|\$)\s*", re.IGNORECASE)
_PLAIN_NUMBER = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


def cimb_quote(rate: float, amount_sgd: float) -> Quote:
    return Quote("cimb", amount_sgd, 0.0, round(amount_sgd * rate, 2))


def wise_quote(rate: float, fee: WiseFee, amount_sgd: float) -> Quote:
    fee_sgd = fee.fee_for(amount_sgd)
    received = max(0.0, (amount_sgd - fee_sgd) * rate)
    return Quote("wise", amount_sgd, round(fee_sgd, 2), round(received, 2))


def quotes_for(state: RateState, amount_sgd: float) -> list[Quote]:
    quotes: list[Quote] = []
    if state.cimb_rate is not None:
        quotes.append(cimb_quote(state.cimb_rate, amount_sgd))
    if state.wise_rate is not None:
        quotes.append(wise_quote(state.wise_rate, state.wise_fee, amount_sgd))
    return sorted(quotes, key=lambda q: q.received_myr, reverse=True)


def switch_point(cimb_rate: float, wise_rate: float, fee: WiseFee) -> SwitchPoint:
    denom = wise_rate * (1 - fee.pct) - cimb_rate
    if denom <= 0:
        return SwitchPoint("cimb_all", None)
    a_star = fee.fixed_sgd * wise_rate / denom
    if a_star <= 100:
        return SwitchPoint("wise_all", None)
    return SwitchPoint("split", round(a_star / 10) * 10.0)


def switch_text(sp: SwitchPoint) -> str:
    if sp.kind == "cimb_all":
        return "CIMB best at every amount"
    if sp.kind == "wise_all":
        return "Wise best at every amount"
    return f"Under SGD {sp.amount_sgd:,.0f} → CIMB · above → Wise"


def parse_amount(text: str) -> float | None:
    cleaned = _AMOUNT_PREFIX.sub("", text.strip()).replace(",", "").strip()
    if not _PLAIN_NUMBER.match(cleaned):
        return None
    amount = float(cleaned)
    if not math.isfinite(amount) or not AMOUNT_MIN_SGD <= amount <= AMOUNT_MAX_SGD:
        return None
    return amount
