import asyncio
from datetime import datetime, timedelta, timezone

import ui
from bot import build_bot, commands_hash, register_commands
from db import Database
from models import RateState
from settings import Secrets


def run(coro_fn):
    return asyncio.run(coro_fn())


def _bot():
    return build_bot(Database(":memory:"), RateState(), Secrets("x", None))


def test_command_set():
    async def go():
        bot = _bot()
        await register_commands(bot)
        return sorted(c.name for c in bot.tree.get_commands())

    assert run(go) == ["a", "f", "reg", "t"]


def test_commands_hash_stable_and_sensitive():
    async def go():
        bot = _bot()
        await register_commands(bot)
        h1, h2 = commands_hash(bot.tree), commands_hash(bot.tree)
        bot.tree.remove_command("t")
        return h1, h2, commands_hash(bot.tree)

    h1, h2, h3 = run(go)
    assert h1 == h2 and h1 != h3


def test_alert_view_is_persistent():
    async def go():
        return ui.AlertView(Database(":memory:"), RateState())

    view = run(go)
    assert view.timeout is None
    ids = {getattr(item, "custom_id", None) for item in view.children}
    assert {"alert:compare", "alert:snooze"} <= ids
    assert any(getattr(item, "url", None) == "https://wise.com/send" for item in view.children)


def test_compare_select_options():
    async def go():
        return ui.CompareSelect(render=None, custom_id="x", selected=1000)

    select = run(go)
    assert [o.value for o in select.options] == ["200", "500", "1000", "2000", "3000", "other"]
    assert [o.label for o in select.options][2] == "SGD 1,000"
    assert [o.default for o in select.options][2] is True


def _panel_labels(enabled, snoozed_until=None):
    async def go():
        db = Database(":memory:")
        db.create_user("1", "S")
        db.update_user("1", enabled=enabled, snoozed_until=snoozed_until)
        view = ui.PanelView(db, RateState(), "1", 1000)
        return [getattr(item, "label", None) for item in view.children]

    return run(go)


def test_panel_view_buttons():
    labels = _panel_labels(True)
    assert "🎯 Target" in labels and "🔔 Alerts: On" in labels and "🔄 Refresh" in labels
    assert "Unsnooze" not in labels
    assert "🔕 Alerts: Off" in _panel_labels(False)


def test_panel_view_unsnooze_only_when_snoozed():
    later = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    assert "Unsnooze" in _panel_labels(True, later)


# ---- alert DM with chart (Phase 3) ---------------------------------------

import json  # noqa: E402
from pathlib import Path  # noqa: E402

from models import User  # noqa: E402
from notifier import Notifier  # noqa: E402
from providers.wise import parse_wise_history  # noqa: E402

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
        notifier = Notifier(bot, db, state, history_fetcher=history_fetcher)
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


# ---- command sync must never stop the bot from starting --------------------

import discord  # noqa: E402

from bot import sync_commands  # noqa: E402


def test_sync_failures_do_not_raise():
    async def go():
        bot = build_bot(Database(":memory:"), RateState(), Secrets("x", 123))
        await register_commands(bot)

        async def boom(*args, **kwargs):
            raise discord.DiscordException("forbidden")

        bot.tree.sync = boom
        await sync_commands(bot)
        return bot.db.get_meta("commands_hash"), bot.db.get_meta("guild_cleanup_done")

    stored_hash, cleanup_done = asyncio.run(go())
    assert stored_hash is None  # retry the global sync next start
    assert cleanup_done == "1"  # but never retry the cosmetic guild cleanup


def test_sync_success_stores_hash_once():
    calls = []

    async def go():
        bot = build_bot(Database(":memory:"), RateState(), Secrets("x", None))
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
