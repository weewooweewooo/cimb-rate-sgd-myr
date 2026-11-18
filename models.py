"""Plain data types shared across modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import settings


@dataclass
class User:
    discord_user_id: str
    name: str
    target_rate: float
    enabled: bool
    peak_rate: float = 0.0
    last_alerted_at: str | None = None


@dataclass(frozen=True)
class WiseFee:
    fixed_sgd: float
    pct: float  # fraction, e.g. 0.0025 for 0.25%

    def fee_for(self, amount_sgd: float) -> float:
        return self.fixed_sgd + self.pct * amount_sgd


@dataclass(frozen=True)
class Quote:
    provider: str  # "cimb" | "wise"
    amount_sgd: float
    fee_sgd: float
    received_myr: float

    @property
    def effective_rate(self) -> float:
        return self.received_myr / self.amount_sgd


@dataclass(frozen=True)
class SwitchPoint:
    kind: str  # "split" | "cimb_all" | "wise_all"
    amount_sgd: float | None


def _default_wise_fee() -> WiseFee:
    return WiseFee(settings.WISE_DEFAULT_FEE_FIXED_SGD, settings.WISE_DEFAULT_FEE_PCT)


@dataclass
class RateState:
    cimb_rate: float | None = None
    cimb_at: datetime | None = None
    wise_rate: float | None = None
    wise_at: datetime | None = None
    wise_fee: WiseFee = field(default_factory=_default_wise_fee)
    fee_checked_on: date | None = None
