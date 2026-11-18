from datetime import datetime, timedelta, timezone

from embeds import alert_preview_text, build_alert_embed, build_panel_embed, format_age, format_myr
from models import RateState, User

NOW = datetime(2026, 11, 18, 3, 0, tzinfo=timezone.utc)  # 11:00 SGT
USER = User("1", "Sean", 3.16, True)
BOTH = dict(cimb_rate=3.1695, wise_rate=3.17866)


def test_format_myr():
    assert format_myr(3169.5) == "RM 3,169.50"


def test_format_age():
    assert format_age(None, NOW) == "no data yet"
    assert format_age(NOW - timedelta(seconds=20), NOW) == "updated just now"
    assert format_age(NOW - timedelta(seconds=70), NOW) == "updated 1 min ago"
    assert format_age(NOW - timedelta(minutes=5), NOW) == "updated 5 min ago"


def test_alert_embed_both_providers():
    e = build_alert_embed(USER, RateState(**BOTH), 1000, NOW)
    assert e.title == "💱 Target hit: 3.1695 effective (CIMB)"
    assert e.description == "Mid-market 3.1787 · your target 3.1600"
    assert e.fields[0].name == "For SGD 1,000:"
    body = e.fields[0].value
    assert "🥇 CIMB" in body and "RM 3,169.50" in body
    assert "🥈 Wise" in body and "fee SGD 3.03" in body
    assert "💡 Under SGD 1,390 → CIMB · above → Wise" in body


def test_alert_embed_other_amount_reranks():
    e = build_alert_embed(USER, RateState(**BOTH), 3000, NOW)
    assert e.fields[0].name == "For SGD 3,000:"
    assert e.fields[0].value.splitlines()[0].startswith("🥇 Wise")


def test_alert_embed_cimb_only_has_no_switch_line():
    e = build_alert_embed(USER, RateState(cimb_rate=3.17), 1000, NOW)
    assert "💡" not in e.fields[0].value
    assert "Mid-market" not in (e.description or "")


def test_alert_embed_no_rates():
    e = build_alert_embed(USER, RateState(), 1000, NOW)
    assert e.fields[0].value == "No rates right now."


def test_preview_text():
    assert alert_preview_text(RateState(cimb_rate=3.1701)) == "SGD → MYR: 3.1701 (CIMB)"
    assert alert_preview_text(RateState()) == "SGD → MYR: no rate"


def test_panel_shows_alert_state_and_amount():
    state = RateState(**BOTH, cimb_at=NOW - timedelta(seconds=70))
    e = build_panel_embed(USER, state, 3000, NOW)
    assert e.title == "⚙️ SGD → MYR · updated 1 min ago"
    assert "CIMB 3.1695 · Wise 3.1787 (fee 0.53 + 0.25%)" in e.description
    assert "Your target 3.1600 · Alerts 🔔 On" in e.description
    assert "For SGD 3,000:  Wise RM 9,510.46 · CIMB RM 9,508.50" in e.description


def test_panel_disabled_and_snoozed():
    user = User("1", "Sean", 3.16, False, snoozed_until=(NOW + timedelta(minutes=30)).isoformat())
    e = build_panel_embed(user, RateState(cimb_rate=3.17), 1000, NOW)
    assert "Alerts 🔕 Off" in e.description
    assert "😴 Snoozed until 11:30" in e.description


def test_panel_no_data():
    e = build_panel_embed(USER, RateState(), 1000, NOW)
    assert e.title == "⚙️ SGD → MYR · no data yet"
    assert "No rates yet" in e.description


def test_help_embed_lists_every_command():
    from embeds import build_help_embed

    e = build_help_embed()
    text = e.description + "".join(f.name + f.value for f in e.fields)
    for cmd in ("/reg", "/f", "/t", "/a", "/help"):
        assert cmd in text
    assert "Mon–Fri" in text and "9am–8pm" in text
    assert "Compare" in text and "Snooze" in text
