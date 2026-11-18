import json
from datetime import timedelta
from pathlib import Path

import pytest

from chart import caption, likely_band, percentile_rank, render_chart
from providers import ProviderError
from providers.wise import parse_wise_history

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
