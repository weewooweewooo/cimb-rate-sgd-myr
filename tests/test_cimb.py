from pathlib import Path

import pytest

from providers import ProviderError
from providers.cimb import parse_cimb_rate

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
