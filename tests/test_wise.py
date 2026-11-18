import json
from pathlib import Path

import pytest

from providers import ProviderError
from providers.wise import parse_wise_fee, parse_wise_live

FIXTURES = Path(__file__).parent / "fixtures"
LIVE = FIXTURES / "wise_live.json"
PRICE = FIXTURES / "wise_price_1000.json"


def test_live():
    assert parse_wise_live(json.loads(LIVE.read_text())) == 3.17894


@pytest.mark.parametrize("bad", [{}, {"value": "x"}, {"value": 0}, [], "<html>", None])
def test_live_rejects(bad):
    with pytest.raises(ProviderError):
        parse_wise_live(bad)


def test_fee_cheapest_bank_payout_not_card():
    fee = parse_wise_fee(json.loads(PRICE.read_text()), 1000)
    assert fee.pct == pytest.approx(0.0025)
    assert fee.fixed_sgd == pytest.approx(0.53)


def test_fee_picks_cheapest_allowed():
    entries = [
        {"payInMethod": "RECEIVE_BANK_TRANSFER", "payOutMethod": "BANK_TRANSFER", "total": 3.50, "variableFeePercent": 0.30},
        {"payInMethod": "PAYNOW", "payOutMethod": "BANK_TRANSFER", "total": 3.03, "variableFeePercent": 0.25},
    ]
    assert parse_wise_fee(entries, 1000).fixed_sgd == pytest.approx(0.53)


@pytest.mark.parametrize(
    "entries",
    [
        [{"payInMethod": "VISA_CREDIT", "payOutMethod": "BANK_TRANSFER", "total": 44, "variableFeePercent": 4.54}],
        [],
        {"error": "x"},
        [{"payInMethod": "PAYNOW", "payOutMethod": "BANK_TRANSFER", "total": "x", "variableFeePercent": 0.25}],
    ],
)
def test_fee_rejects(entries):
    with pytest.raises(ProviderError):
        parse_wise_fee(entries, 1000)
