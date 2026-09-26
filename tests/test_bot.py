"""Tests for bot.py that run without connecting to Discord."""

from bot import BotApp
from config import Config
from localization import LOCALES


def test_bot_uses_configured_locale() -> None:
    # Any non-silent locale works, because every bot ships a different set of languages.
    locale = next(key for key in LOCALES if key != "silent")
    bot = BotApp(Config(discord_token="t", locale=locale))
    assert bot.strings is LOCALES[locale]
    assert bot.intents.members


def test_unknown_locale_falls_back_to_silent() -> None:
    bot = BotApp(Config(discord_token="t", locale="xx"))
    assert bot.strings is LOCALES["silent"]
