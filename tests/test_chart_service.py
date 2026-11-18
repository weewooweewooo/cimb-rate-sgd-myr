import asyncio
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import discord

import ui
from chart_service import ChartMaker, wise_net_series
from db import Database
from models import RateState, User, WiseFee
from providers.wise import parse_wise_history

HISTORY = parse_wise_history(json.loads((Path(__file__).parent / "fixtures" / "wise_history.json").read_text()))
NOW = HISTORY[-1][0]
STATE = RateState(cimb_rate=3.17, wise_rate=3.18)


def test_wise_net_series_uses_fee():
    (point,) = wise_net_series([(NOW, 3.18802)], WiseFee(0.53, 0.0025), 1000)
    assert point[0] == NOW and round(point[1], 5) == round(3.18802 * (1000 - 3.03) / 1000, 5)


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_history_cached_for_ten_minutes():
    calls, clock = [], Clock()

    async def fetch():
        calls.append(1)
        return HISTORY

    async def go():
        maker = ChartMaker(fetch, Database(":memory:"), clock=clock)
        first = await maker.make(3.16, STATE, NOW)
        clock.t = 599
        await maker.make(3.16, STATE, NOW)
        clock.t = 601
        await maker.make(3.16, STATE, NOW)
        return first

    first = asyncio.run(go())
    assert isinstance(first, discord.File) and first.filename == "chart.png"
    assert len(calls) == 2


def test_no_chart_without_wise_or_when_fetch_fails():
    async def boom():
        raise RuntimeError("wise down")

    async def ok():
        return HISTORY

    async def go():
        no_wise = await ChartMaker(ok, Database(":memory:")).make(3.16, RateState(cimb_rate=3.17), NOW)
        failing = await ChartMaker(boom, Database(":memory:")).make(3.16, STATE, NOW)
        return no_wise, failing

    assert asyncio.run(go()) == (None, None)


# ---- /f panel shows the chart ----------------------------------------------


class FakeChartMaker:
    def __init__(self, available=True):
        self.available = available

    async def make(self, target, state, now):
        return discord.File(__import__("io").BytesIO(b"png"), filename="chart.png") if self.available else None


class FakeResponse:
    def __init__(self):
        self.deferred = []
        self.messages = []

    async def defer(self, **kwargs):
        self.deferred.append(kwargs)

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class FakeInteraction:
    def __init__(self):
        self.response = FakeResponse()
        self.edits, self.followups = [], []
        self.followup = SimpleNamespace(send=self._followup)

    async def _followup(self, **kwargs):
        self.followups.append(kwargs)

    async def edit_original_response(self, **kwargs):
        self.edits.append(kwargs)


def _db():
    db = Database(":memory:")
    db.create_user("1", "S")
    return db


def test_f_opens_with_chart():
    async def go():
        i = FakeInteraction()
        await ui.show_panel(i, _db(), STATE, "1", 1000, FakeChartMaker(), edit=False)
        return i

    i = asyncio.run(go())
    assert i.response.deferred == [{"ephemeral": True, "thinking": True}]
    (sent,) = i.followups
    assert sent["ephemeral"] is True
    assert sent["embed"].image.url == "attachment://chart.png"
    assert [f.filename for f in sent["files"]] == ["chart.png"]


def test_panel_update_replaces_chart():
    async def go():
        i = FakeInteraction()
        await ui.show_panel(i, _db(), STATE, "1", 3000, FakeChartMaker(), edit=True)
        return i

    i = asyncio.run(go())
    assert i.response.deferred == [{}]
    (edit,) = i.edits
    assert [f.filename for f in edit["attachments"]] == ["chart.png"]
    assert "For SGD 3,000" in edit["embed"].description


def test_panel_without_chart_still_works():
    async def go():
        i = FakeInteraction()
        await ui.show_panel(i, _db(), STATE, "1", 1000, FakeChartMaker(available=False), edit=False)
        return i

    (sent,) = asyncio.run(go()).followups
    assert sent["embed"].image.url is None and sent["files"] == []


def test_unregistered_user_gets_message_not_panel():
    async def go():
        i = FakeInteraction()
        await ui.show_panel(i, Database(":memory:"), STATE, "1", 1000, FakeChartMaker(), edit=False)
        return i

    i = asyncio.run(go())
    assert i.response.messages and not i.followups and not i.response.deferred


# ---- alert Compare keeps its chart -----------------------------------------


def test_keep_chart_on_alert_edit():
    embed = discord.Embed(title="x")
    message = SimpleNamespace(attachments=[SimpleNamespace(filename="chart.png")])
    ui.keep_chart(embed, message)
    assert embed.image.url == "attachment://chart.png"

    plain = discord.Embed(title="y")
    ui.keep_chart(plain, SimpleNamespace(attachments=[]))
    assert plain.image.url is None
