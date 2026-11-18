import pytest

import settings
from models import Quote, WiseFee


def test_load_secrets_requires_token(monkeypatch):
    monkeypatch.setattr(settings, "load_dotenv", lambda: None)
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="DISCORD_BOT_TOKEN is required"):
        settings.load_secrets()


def test_load_secrets_optional_guild(monkeypatch):
    monkeypatch.setattr(settings, "load_dotenv", lambda: None)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "x")
    monkeypatch.delenv("DISCORD_GUILD_ID", raising=False)
    assert settings.load_secrets() == settings.Secrets("x", None)
    monkeypatch.setenv("DISCORD_GUILD_ID", "123")
    assert settings.load_secrets().discord_guild_id == 123


def test_wise_fee_for():
    assert WiseFee(0.53, 0.0025).fee_for(1000) == pytest.approx(3.03)


def test_quote_effective_rate():
    assert Quote("cimb", 1000, 0, 3169.5).effective_rate == pytest.approx(3.1695)
