"""Pure logic: settings, schedule, rate parsing, money maths, alerts, storage, monitor loop, chart maths."""
import pytest
import settings
from models import Quote, WiseFee
from datetime import datetime, timezone
from schedule import is_active, seconds_until_next_window
from settings import TIMEZONE
from pathlib import Path
from providers import ProviderError
from providers.cimb import parse_cimb_rate
import json
from providers.wise import parse_wise_fee, parse_wise_live
from compare import cimb_quote, parse_amount, quotes_for, switch_point, switch_text, wise_quote
from models import RateState, SwitchPoint, WiseFee
from datetime import datetime, timedelta, timezone
from alerts import decide
from models import User
from db import Database
from models import WiseFee
import asyncio
import logging
from models import RateState
from monitor import FetchHealth, Fetchers, evaluate_users, poll_once
from compare import quotes_for
from datetime import timedelta
from chart import caption, likely_band, percentile_rank, render_chart
from providers.wise import parse_wise_history


# ---- settings & models -----------------------------------------------------


def test_load_secrets_reads_token(monkeypatch):
    monkeypatch.setattr(settings, "load_dotenv", lambda: None)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "x")
    assert settings.load_secrets() == settings.Secrets("x")


def test_load_secrets_requires_token(monkeypatch):
    monkeypatch.setattr(settings, "load_dotenv", lambda: None)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DISCORD_BOT_TOKEN is required"):
        settings.load_secrets()


def test_wise_fee_for():
    assert WiseFee(0.53, 0.0025).fee_for(1000) == pytest.approx(3.03)


def test_quote_effective_rate():
    assert Quote("cimb", 1000, 0, 3169.5).effective_rate == pytest.approx(3.1695)


# ---- schedule --------------------------------------------------------------


def sgt(y, m, d, hh, mm):  # 2026-11-20 is a Friday
    return datetime(y, m, d, hh, mm, tzinfo=TIMEZONE).astimezone(timezone.utc)


def test_active_boundaries():
    assert is_active(sgt(2026, 11, 20, 19, 59))
    assert not is_active(sgt(2026, 11, 20, 20, 0))
    assert not is_active(sgt(2026, 11, 21, 12, 0))  # Saturday
    assert is_active(sgt(2026, 11, 23, 9, 0))  # Monday
    assert not is_active(sgt(2026, 11, 23, 8, 59))


def test_next_window_from_friday_evening():
    assert seconds_until_next_window(sgt(2026, 11, 20, 20, 0)) == 61 * 3600


def test_next_window_same_morning():
    assert seconds_until_next_window(sgt(2026, 11, 23, 8, 30)) == 30 * 60


def test_next_window_when_active_is_zero():
    assert seconds_until_next_window(sgt(2026, 11, 23, 10, 0)) == 0.0


# ---- CIMB provider ---------------------------------------------------------


FIXTURE = Path(__file__).parent / "fixtures" / "cimb_page.html"


def test_parse_fixture():
    assert parse_cimb_rate(FIXTURE.read_text()) == 3.1695


@pytest.mark.parametrize(
    "html",
    [
        "<html></html>",
        '<input name="x_rateList" value="[]" />',
        '<input name="x_rateList" value="[abc]" />',
        '<input name="x_rateList" value="[0]" />',
    ],
)
def test_parse_rejects(html):
    with pytest.raises(ProviderError):
        parse_cimb_rate(html)


def test_parse_multi_values_takes_first():
    assert parse_cimb_rate('<input name="a_rateList" value="[3.17, 3.18]" />') == 3.17


# ---- Wise provider ---------------------------------------------------------


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


# ---- compare maths ---------------------------------------------------------


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


# ---- alert decision --------------------------------------------------------


NOW = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)


def u(**kw):
    fields = {"target_rate": 3.16, "enabled": True, **kw}
    return User("1", "a", **fields)


def test_first_alert_at_target():
    assert decide(u(), 3.16, NOW) == "alert"


def test_step_required():
    assert decide(u(peak_rate=3.1600), 3.1609, NOW) == "none"
    assert decide(u(peak_rate=3.1600), 3.1610, NOW) == "alert"


def test_reset_below_target():
    assert decide(u(peak_rate=3.17), 3.1599, NOW) == "reset"


def test_below_target_no_peak():
    assert decide(u(), 3.15, NOW) == "none"


def test_disabled():
    assert decide(u(enabled=False), 3.20, NOW) == "none"


def test_snoozed():
    later = (NOW + timedelta(minutes=30)).isoformat()
    assert decide(u(snoozed_until=later), 3.20, NOW) == "none"
    earlier = (NOW - timedelta(minutes=1)).isoformat()
    assert decide(u(snoozed_until=earlier), 3.20, NOW) == "alert"


# ---- SQLite storage --------------------------------------------------------


def test_user_crud():
    db = Database(":memory:")
    assert db.create_user("1", "Sean")
    assert not db.create_user("1", "Sean")
    assert db.get_user("1").target_rate == 3.1
    assert db.update_user("1", target_rate=3.16, enabled=False)
    assert db.get_user("1").enabled is False
    assert db.get_user("1").target_rate == 3.16
    assert not db.update_user("missing", enabled=True)
    with pytest.raises(ValueError):
        db.update_user("1", bogus=1)


def test_list_users():
    db = Database(":memory:")
    db.create_user("1", "A")
    db.create_user("2", "B")
    assert sorted(u.discord_user_id for u in db.list_users()) == ["1", "2"]


def test_record_rate_only_on_change():
    db = Database(":memory:")
    assert db.record_rate("cimb", 3.17, NOW)
    assert not db.record_rate("cimb", 3.17, NOW + timedelta(minutes=1))
    assert db.record_rate("cimb", 3.18, NOW + timedelta(minutes=2))
    assert db.record_rate("wise", 3.17, NOW)
    assert [r for _, r in db.rates_since("cimb", NOW)] == [3.17, 3.18]
    assert db.rates_since("cimb", NOW)[0][0] == NOW


def test_wise_fee_roundtrip():
    db = Database(":memory:")
    assert db.latest_wise_fee() is None
    db.save_wise_fee(WiseFee(0.53, 0.0025), NOW)
    db.save_wise_fee(WiseFee(0.53, 0.0025), NOW + timedelta(days=1))
    assert db.latest_wise_fee() == WiseFee(0.53, 0.0025)
    db.save_wise_fee(WiseFee(0.60, 0.0026), NOW + timedelta(days=2))
    assert db.latest_wise_fee() == WiseFee(0.60, 0.0026)


def test_meta():
    db = Database(":memory:")
    assert db.get_meta("k") is None
    db.set_meta("k", "v1")
    db.set_meta("k", "v2")
    assert db.get_meta("k") == "v2"


def test_file_db_persists(tmp_path):
    path = tmp_path / "sub" / "rates.db"
    Database(path).create_user("1", "A")
    assert Database(path).get_user("1").name == "A"


def test_prune():
    db = Database(":memory:")
    db.record_rate("cimb", 3.1, NOW - timedelta(days=91))
    db.record_rate("cimb", 3.2, NOW)
    assert db.prune(NOW - timedelta(days=90)) == 1


# ---- monitor loop ----------------------------------------------------------


def const(value):
    async def fetch():
        return value
    return fetch


def failing(msg="boom"):
    async def fetch(*_):
        raise ProviderError(msg)
    return fetch


class FakeSender:
    def __init__(self, ok=True):
        self.ok = ok
        self.sent = []

    async def send_alert(self, user, state):
        self.sent.append((user.discord_user_id, state.cimb_rate))
        return self.ok


def test_poll_updates_state_and_db():
    db, state = Database(":memory:"), RateState()
    asyncio.run(poll_once(Fetchers(cimb=const(3.17)), db, state, FetchHealth(), NOW))
    assert state.cimb_rate == 3.17 and state.cimb_at == NOW
    assert db.rates_since("cimb", NOW) == [(NOW, 3.17)]


def test_cimb_failure_clears_rate():
    db, state = Database(":memory:"), RateState(cimb_rate=3.17)
    asyncio.run(poll_once(Fetchers(cimb=failing()), db, state, FetchHealth(), NOW))
    assert state.cimb_rate is None


def test_failure_logged_once_then_recovery(caplog):
    caplog.set_level(logging.WARNING)
    h = FetchHealth()
    for _ in range(5):
        h.failed("cimb", "boom")
    h.ok("cimb")
    h.ok("cimb")
    assert [r.levelname for r in caplog.records] == ["ERROR", "WARNING"]


def _db_with_user(peak=0.0):
    db = Database(":memory:")
    db.create_user("1", "S", target_rate=3.16)
    db.update_user("1", peak_rate=peak)
    return db


def test_evaluate_sends_and_sets_peak():
    db, sender = _db_with_user(), FakeSender()
    asyncio.run(evaluate_users(db, sender, RateState(cimb_rate=3.17), NOW))
    assert sender.sent == [("1", 3.17)]
    user = db.get_user("1")
    assert user.peak_rate == 3.17 and user.last_alerted_at == NOW.isoformat()


def test_evaluate_failed_send_keeps_peak():
    db, sender = _db_with_user(), FakeSender(ok=False)
    asyncio.run(evaluate_users(db, sender, RateState(cimb_rate=3.17), NOW))
    assert db.get_user("1").peak_rate == 0.0


def test_evaluate_reset():
    db, sender = _db_with_user(peak=3.17), FakeSender()
    asyncio.run(evaluate_users(db, sender, RateState(cimb_rate=3.15), NOW))
    assert sender.sent == [] and db.get_user("1").peak_rate == 0.0


def test_evaluate_no_rates_does_nothing():
    db, sender = _db_with_user(), FakeSender()
    asyncio.run(evaluate_users(db, sender, RateState(), NOW))
    assert sender.sent == []


def fee_fetcher(fee, calls):
    async def fetch(amount):
        calls.append(amount)
        return fee
    return fetch


def test_both_providers_recorded():
    db, state, calls = Database(":memory:"), RateState(), []
    fetchers = Fetchers(cimb=const(3.17), wise_live=const(3.18), wise_fee=fee_fetcher(WiseFee(0.6, 0.003), calls))
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW))
    assert state.wise_rate == 3.18 and state.wise_at == NOW
    assert db.rates_since("wise", NOW) == [(NOW, 3.18)]
    assert state.wise_fee == WiseFee(0.6, 0.003) and db.latest_wise_fee() == WiseFee(0.6, 0.003)
    assert calls == [1000.0]


def test_wise_failure_keeps_cimb_only():
    db, state = Database(":memory:"), RateState(wise_rate=3.18)
    fetchers = Fetchers(cimb=const(3.17), wise_live=failing(), wise_fee=fee_fetcher(WiseFee(0.53, 0.0025), []))
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW))
    assert state.wise_rate is None
    assert [q.provider for q in quotes_for(state, 1000)] == ["cimb"]


def test_fee_checked_once_per_day():
    db, state, calls = Database(":memory:"), RateState(), []
    fetchers = Fetchers(cimb=const(3.17), wise_live=const(3.18), wise_fee=fee_fetcher(WiseFee(0.53, 0.0025), calls))
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW))
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW.replace(hour=8)))  # same SGT day (16:00)
    assert len(calls) == 1
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW.replace(day=19)))
    assert len(calls) == 2


def test_fee_check_failure_keeps_previous_fee():
    db, state = Database(":memory:"), RateState(wise_fee=WiseFee(0.7, 0.004))
    fetchers = Fetchers(cimb=const(3.17), wise_live=const(3.18), wise_fee=failing())
    asyncio.run(poll_once(fetchers, db, state, FetchHealth(), NOW))
    assert state.wise_fee == WiseFee(0.7, 0.004)
    assert state.fee_checked_on is not None


# ---- chart maths & rendering -----------------------------------------------


HIST = Path(__file__).parent / "fixtures" / "wise_history.json"


HISTORY = parse_wise_history(json.loads(HIST.read_text()))


def test_parse_history():
    assert len(HISTORY) > 600
    assert HISTORY[0][0].tzinfo is not None
    assert HISTORY == sorted(HISTORY)


@pytest.mark.parametrize("bad", [{}, [{"value": "x", "time": 1}], "<html>"])
def test_parse_history_rejects(bad):
    with pytest.raises(ProviderError):
        parse_wise_history(bad)


def test_band_contains_current():
    lo, hi = likely_band(HISTORY, 3.17)
    assert lo < 3.17 < hi
    assert (hi - lo) / 3.17 < 0.02


def test_band_with_too_little_history():
    assert likely_band(HISTORY[:3], 3.17) == (3.17, 3.17)


def test_percentile_bounds():
    assert percentile_rank(HISTORY, 0) == 0
    assert percentile_rank(HISTORY, 99) == 100


def test_caption_is_honest():
    text = caption(3.1848, 72)
    assert text == "Mid-market 3.1848 is higher than 72% of the last 30 days · shaded = likely range next 24 h, not a forecast"


def test_render_png():
    end = HISTORY[-1][0]
    cimb = [(end - timedelta(hours=5), 3.170), (end - timedelta(hours=2), 3.172)]
    png = render_chart(HISTORY[-168:], cimb, 3.16, 3.18, (3.175, 3.185), 72)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_dates_shown_in_singapore_time():
    from chart import date_formatter
    from settings import TIMEZONE

    assert date_formatter().tz == TIMEZONE


def test_series_labels_show_latest_values():
    from datetime import datetime, timezone

    from chart import series_labels

    t = datetime(2026, 11, 18, 4, tzinfo=timezone.utc)
    labels = series_labels(mid=[(t, 3.18802)], wise_net=[(t, 3.17836)], cimb=[(t, 3.1796)], target=3.19)
    assert labels == {
        "mid": "Wise mid-market (before fee)  3.1880",
        "net": "Wise after fees, SGD 1,000  3.1784",
        "cimb": "CIMB  3.1796",
        "target": "Your target  3.1900",
    }


def test_series_labels_skip_missing():
    from chart import series_labels

    assert set(series_labels(mid=[], wise_net=[], cimb=[], target=3.19)) == {"target"}


def test_render_png_with_wise_net():
    end = HISTORY[-1][0]
    net = [(t, v * 0.997) for t, v in HISTORY[-168:]]
    png = render_chart(HISTORY[-168:], [(end, 3.17)], 3.16, 3.18, (3.175, 3.185), 72, wise_net=net)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
