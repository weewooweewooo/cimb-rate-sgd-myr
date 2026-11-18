"""Discord side: embeds, commands, panel and alert views, notifier, chart attachments, entrypoint wiring."""
from datetime import datetime, timedelta, timezone
from embeds import alert_preview_text, build_alert_embed, build_panel_embed, format_myr
from models import RateState, User
import asyncio
import ui
from bot import build_bot, commands_hash, register_commands
from db import Database
from models import RateState
from settings import Secrets
import json
from pathlib import Path
from models import User
from chart_service import ChartMaker
from notifier import Notifier
from providers.wise import parse_wise_history
import discord
from bot import sync_commands
import agent
from monitor import Fetchers
from datetime import timedelta
from types import SimpleNamespace
from chart_service import ChartMaker, wise_net_series
from models import RateState, User, WiseFee


# ---- embeds ----------------------------------------------------------------


NOW = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)


USER = User("1", "Sean", 3.16, True)


BOTH = dict(cimb_rate=3.1695, wise_rate=3.17866)


def test_format_myr():
    assert format_myr(3169.5) == "RM 3,169.50"


# ---- commands, views, notifier ---------------------------------------------


def run(coro_fn):
    return asyncio.run(coro_fn())


def _bot():
    return build_bot(Database(":memory:"), RateState(), Secrets("x"))


def test_command_set():
    async def go():
        bot = _bot()
        await register_commands(bot)
        return sorted(c.name for c in bot.tree.get_commands())

    assert run(go) == ["a", "f", "help", "reg", "t"]


def test_commands_hash_stable_and_sensitive():
    async def go():
        bot = _bot()
        await register_commands(bot)
        h1, h2 = commands_hash(bot.tree), commands_hash(bot.tree)
        bot.tree.remove_command("t")
        return h1, h2, commands_hash(bot.tree)

    h1, h2, h3 = run(go)
    assert h1 == h2 and h1 != h3


def test_compare_select_options():
    async def go():
        return ui.CompareSelect(render=None, custom_id="x", selected=1000)

    select = run(go)
    assert [o.value for o in select.options] == ["200", "500", "1000", "2000", "3000", "other"]
    assert [o.label for o in select.options][2] == "SGD 1,000"
    assert [o.default for o in select.options][2] is True


HISTORY = parse_wise_history(json.loads((Path(__file__).parent / "fixtures" / "wise_history.json").read_text()))


class FakeDM:
    def __init__(self):
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)


class FakeBot:
    def __init__(self):
        self.dm = FakeDM()

    def get_user(self, _uid):
        return self.dm


def _send(history_fetcher):
    async def go():
        bot, db = FakeBot(), Database(":memory:")
        state = RateState(cimb_rate=3.17, wise_rate=3.18)
        notifier = Notifier(bot, db, state, chart_maker=ChartMaker(history_fetcher, db))
        ok = await notifier.send_alert(User("1", "S", 3.16, True), state)
        return ok, bot.dm.sent

    return asyncio.run(go())


def test_alert_with_chart():
    async def history():
        return HISTORY

    ok, sent = _send(history)
    assert ok and len(sent) == 1
    assert sent[0]["file"].filename == "chart.png"
    assert sent[0]["embed"].image.url == "attachment://chart.png"
    assert sent[0]["content"].startswith("SGD → MYR:")


def test_alert_without_chart_when_history_fails():
    async def history():
        raise RuntimeError("wise down")

    ok, sent = _send(history)
    assert ok and len(sent) == 1
    assert "file" not in sent[0]
    assert sent[0]["embed"].image.url is None


def test_sync_failures_do_not_raise():
    async def go():
        bot = build_bot(Database(":memory:"), RateState(), Secrets("x"))
        await register_commands(bot)

        async def boom(*args, **kwargs):
            raise discord.DiscordException("forbidden")

        bot.tree.sync = boom
        await sync_commands(bot)
        return bot.db.get_meta("commands_hash")

    assert asyncio.run(go()) is None  # not stored, so the sync is retried next start


def test_sync_success_stores_hash_once():
    calls = []

    async def go():
        bot = build_bot(Database(":memory:"), RateState(), Secrets("x"))
        await register_commands(bot)

        async def ok(*args, **kwargs):
            calls.append(kwargs)
            return []

        bot.tree.sync = ok
        await sync_commands(bot)
        await sync_commands(bot)
        return bot.db.get_meta("commands_hash"), commands_hash(bot.tree)

    stored, expected = asyncio.run(go())
    assert stored == expected and len(calls) == 1


def test_dm_failure_logged_once_per_user(caplog):
    import logging

    class BrokenDM:
        async def send(self, **kwargs):
            raise discord.DiscordException("cannot DM this user")

    class Bot:
        def get_user(self, _uid):
            return BrokenDM()

    async def go():
        db, state = Database(":memory:"), RateState(cimb_rate=3.17)
        notifier = Notifier(Bot(), db, state)
        user = User("1", "S", 3.16, True)
        return [await notifier.send_alert(user, state) for _ in range(3)]

    caplog.set_level(logging.WARNING)
    assert asyncio.run(go()) == [False, False, False]
    assert len([r for r in caplog.records if r.levelname == "ERROR"]) == 1


# ---- entrypoint wiring -----------------------------------------------------


def test_make_fetchers_wires_cimb():
    async def go():
        async with agent.make_session() as session:
            fetchers = agent.make_fetchers(session)
            return fetchers, session.headers.get("User-Agent", "")

    fetchers, ua = asyncio.run(go())
    assert isinstance(fetchers, Fetchers) and callable(fetchers.cimb)
    assert callable(fetchers.wise_live) and callable(fetchers.wise_fee)
    assert ua.startswith("Mozilla/5.0")


def test_initial_state_uses_saved_wise_fee():
    from db import Database
    from models import WiseFee

    db = Database(":memory:")
    assert agent.initial_state(db).wise_fee == WiseFee(0.53, 0.0025)
    db.save_wise_fee(WiseFee(0.6, 0.003), __import__("datetime").datetime(2026, 11, 18))
    assert agent.initial_state(db).wise_fee == WiseFee(0.6, 0.003)


def test_make_history_fetcher_is_callable():
    async def go():
        async with agent.make_session() as session:
            return agent.make_history_fetcher(session)

    assert callable(asyncio.run(go()))


# ---- chart service & /f panel chart ----------------------------------------


CHART_NOW = HISTORY[-1][0]


STATE = RateState(cimb_rate=3.17, wise_rate=3.18)


def test_wise_net_series_uses_fee():
    (point,) = wise_net_series([(CHART_NOW, 3.18802)], WiseFee(0.53, 0.0025), 1000)
    assert point[0] == CHART_NOW and round(point[1], 5) == round(3.18802 * (1000 - 3.03) / 1000, 5)


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
        first = await maker.make(3.16, STATE, CHART_NOW)
        clock.t = 599
        await maker.make(3.16, STATE, CHART_NOW)
        clock.t = 601
        await maker.make(3.16, STATE, CHART_NOW)
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
        no_wise = await ChartMaker(ok, Database(":memory:")).make(3.16, RateState(cimb_rate=3.17), CHART_NOW)
        failing = await ChartMaker(boom, Database(":memory:")).make(3.16, STATE, CHART_NOW)
        return no_wise, failing

    assert asyncio.run(go()) == (None, None)


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
    assert edit["embed"].fields[0].name == "For SGD 3,000"


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


def test_keep_chart_on_alert_edit():
    embed = discord.Embed(title="x")
    message = SimpleNamespace(attachments=[SimpleNamespace(filename="chart.png")])
    ui.keep_chart(embed, message)
    assert embed.image.url == "attachment://chart.png"

    plain = discord.Embed(title="y")
    ui.keep_chart(plain, SimpleNamespace(attachments=[]))
    assert plain.image.url is None


def test_no_emoji_in_user_facing_code():
    import re
    from pathlib import Path

    emoji = re.compile("[☀-➿🌀-🫿️]")
    root = Path(__file__).resolve().parent.parent
    offenders = [
        f"{path.name}:{n}"
        for path in root.glob("*.py")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if emoji.search(line)
    ]
    assert offenders == []


# ---- restyled embeds (no emoji, status colour, live timestamps) -------------

from embeds import AMBER, GREEN, GREY, NO_DATA, build_help_embed, change_text, status_color  # noqa: E402


def stamp(dt):
    return f"<t:{int(dt.timestamp())}:R>"


def test_change_text():
    assert change_text(0.0129) == "▲ +0.0129"
    assert change_text(-0.0021) == "▼ -0.0021"
    assert change_text(0.0) == "unchanged"
    assert change_text(None) == ""


def test_status_color():
    assert status_color(3.1695, 3.16) == GREEN
    assert status_color(3.1695, 3.17) == AMBER
    assert status_color(3.1695, 3.18) == GREY
    assert status_color(None, 3.16) == NO_DATA


def test_alert_embed_layout():
    e = build_alert_embed(USER, RateState(**BOTH), 1000, NOW, changes={"cimb": 0.0129, "wise": -0.0021})
    assert e.title is None
    assert e.colour == GREEN
    assert e.description.splitlines() == [
        "-# TARGET HIT · CIMB",
        "## 3.1695 ▲ +0.0129 today",
        "Mid-market 3.1787 ▼ -0.0021 · your target 3.1600",
        f"-# Updated {stamp(NOW)}",
    ]
    field = e.fields[0]
    assert field.name == "For SGD 1,000"
    assert field.value.startswith("```\n1. CIMB   RM 3,169.50\n2. Wise   RM 3,169.03  fee 3.03\n```")
    assert "**Best by amount:** Under SGD 1,390 → CIMB · above → Wise" in field.value
    assert "-# Wise fee SGD 0.53 + 0.25% (cheapest PayNow / bank pay-in)" in field.value


def test_alert_embed_other_amount_reranks():
    e = build_alert_embed(USER, RateState(**BOTH), 3000, NOW)
    assert e.fields[0].name == "For SGD 3,000"
    assert e.fields[0].value.splitlines()[1].startswith("1. Wise")
    assert "## 3.1695" in e.description  # heading stays the reference (SGD 1,000) best rate


def test_alert_embed_cimb_only():
    e = build_alert_embed(USER, RateState(cimb_rate=3.17), 1000, NOW)
    assert "Best by amount" not in e.fields[0].value
    assert "Wise fee" not in e.fields[0].value
    assert "Mid-market" not in e.description
    assert "Your target 3.1600" in e.description


def test_alert_embed_no_rates():
    e = build_alert_embed(USER, RateState(), 1000, NOW)
    assert "No rates right now." in e.description and e.fields == []
    assert e.colour == NO_DATA


def test_preview_text():
    assert alert_preview_text(RateState(cimb_rate=3.1701), 3.16) == "SGD → MYR: 3.1701 (CIMB) · target 3.1600"
    assert alert_preview_text(RateState(), 3.16) == "SGD → MYR: no rate"


def test_panel_layout():
    seen = NOW - timedelta(seconds=70)
    e = build_panel_embed(USER, RateState(**BOTH, cimb_at=seen), 3000, NOW, changes={"cimb": 0.0129, "wise": 0.0110})
    assert e.colour == GREEN
    lines = e.description.splitlines()
    assert lines[0] == f"-# SGD → MYR · updated {stamp(seen)}"
    assert "CIMB  3.1695  ▲ +0.0129" in lines
    assert "Wise  3.1787  ▲ +0.0110  before fee" in lines
    assert any(line.strip().startswith("3.1690") and line.endswith("after fee, SGD 1,000") for line in lines)
    assert "**Best by amount:** Under SGD 1,390 → CIMB · above → Wise" in lines
    assert "Your target **3.1600** · Alerts: **On**" in lines
    field = e.fields[0]
    assert field.name == "For SGD 3,000"
    assert field.value == "```\n1. Wise   RM 9,510.46  fee 8.03\n2. CIMB   RM 9,508.50\n```"


def test_panel_colour_and_alert_off():
    off = User("1", "Sean", 3.17, False)
    e = build_panel_embed(off, RateState(**BOTH), 1000, NOW)
    assert e.colour == AMBER
    assert "Your target **3.1700** · Alerts: **Off**" in e.description


def test_panel_no_data():
    e = build_panel_embed(USER, RateState(), 1000, NOW)
    assert e.description.splitlines()[0] == "-# SGD → MYR · no data yet"
    assert "No rates yet — rates update Mon–Fri, 9am–8pm." in e.description
    assert e.colour == NO_DATA and e.fields == []


def test_help_embed_lists_every_command():
    e = build_help_embed()
    text = e.description + "".join(f.name + f.value for f in e.fields)
    for cmd in ("/reg", "/f", "/t", "/a", "/help"):
        assert cmd in text
    assert "Mon–Fri" in text and "9am–8pm" in text and "Compare" in text
    assert "Snooze" not in text and "Open Wise" not in text


def test_alert_view_only_has_compare():
    async def go():
        return ui.AlertView(Database(":memory:"), RateState())

    view = run(go)
    assert view.timeout is None
    assert [getattr(item, "custom_id", None) for item in view.children] == ["alert:compare"]


def _panel_labels(enabled):
    async def go():
        db = Database(":memory:")
        db.create_user("1", "S")
        db.update_user("1", enabled=enabled)
        view = ui.PanelView(db, RateState(), "1", 1000)
        return [getattr(item, "label", None) for item in view.children]

    return run(go)


def test_panel_view_buttons():
    labels = _panel_labels(True)
    assert labels[:3] == ["Target", "Alerts: On", "Refresh"]
    assert "Alerts: Off" in _panel_labels(False)


def test_today_changes_from_first_reading_of_the_day():
    db = Database(":memory:")
    yesterday = NOW - timedelta(days=1)
    db.record_rate("cimb", 3.10, yesterday)
    db.record_rate("cimb", 3.1796, NOW - timedelta(hours=1))  # 10:00 SGT, first today
    db.record_rate("cimb", 3.1850, NOW)
    changes = ui.today_changes(db, RateState(cimb_rate=3.1925, wise_rate=3.18), NOW)
    assert round(changes["cimb"], 4) == 0.0129
    assert changes.get("wise") is None

