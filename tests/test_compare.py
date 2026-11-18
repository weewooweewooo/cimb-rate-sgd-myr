import pytest

from compare import cimb_quote, parse_amount, quotes_for, switch_point, switch_text, wise_quote
from models import RateState, SwitchPoint, WiseFee

FEE = WiseFee(0.53, 0.0025)


def test_quotes():
    assert cimb_quote(3.1695, 1000).received_myr == 3169.50
    w = wise_quote(3.17866, FEE, 1000)
    assert w.fee_sgd == pytest.approx(3.03)
    assert w.received_myr == 3169.03


def test_wise_quote_never_negative():
    assert wise_quote(3.17866, WiseFee(50, 0.0025), 10).received_myr == 0


def test_quotes_for_ranks_and_skips_missing():
    s = RateState(cimb_rate=3.1695, wise_rate=3.17866, wise_fee=FEE)
    assert [q.provider for q in quotes_for(s, 3000)] == ["wise", "cimb"]
    assert [q.provider for q in quotes_for(s, 200)] == ["cimb", "wise"]
    assert [q.provider for q in quotes_for(RateState(cimb_rate=3.17), 1000)] == ["cimb"]
    assert quotes_for(RateState(), 1000) == []


def test_switch_point_split():
    sp = switch_point(3.1695, 3.17866, FEE)
    assert sp == SwitchPoint("split", 1390.0)
    assert switch_text(sp) == "Under SGD 1,390 → CIMB · above → Wise"


def test_switch_point_cimb_all():
    assert switch_point(3.1720, 3.17866, FEE).kind == "cimb_all"
    assert switch_text(SwitchPoint("cimb_all", None)) == "CIMB best at every amount"


def test_switch_point_wise_all():
    assert switch_point(3.1500, 3.17866, FEE).kind == "wise_all"
    assert switch_text(SwitchPoint("wise_all", None)) == "Wise best at every amount"


@pytest.mark.parametrize(
    "text,expected",
    [("1,523", 1523.0), ("SGD 2000", 2000.0), (" 300 ", 300.0), ("1500.50", 1500.5), ("S$800", 800.0), ("sgd1000", 1000.0)],
)
def test_parse_amount_ok(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", ["abc", "0", "5", "1e9", "", "-100", "inf", "nan", "200000"])
def test_parse_amount_rejects(text):
    assert parse_amount(text) is None
