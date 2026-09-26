"""Tests for bot.py that run without connecting to Discord."""

import logging

import discord

from bot import BotApp, LogFormatter
from config import Config
from localization import LOCALES
from tests.conftest import make_interaction


def test_replies_follow_the_users_language() -> None:
    bot = BotApp(Config(discord_token="t", locale="en"))
    finnish = make_interaction(locale=discord.Locale.finnish)
    assert bot.strings_for(finnish) is LOCALES["fi"]


def test_unknown_language_falls_back_to_bot_locale() -> None:
    bot = BotApp(Config(discord_token="t", locale="fi"))
    japanese = make_interaction(locale=discord.Locale.japanese)
    assert bot.strings_for(japanese) is LOCALES["fi"]


def test_silent_bot_mutes_public_but_not_private_replies() -> None:
    bot = BotApp(Config(discord_token="t", locale="silent"))
    interaction = make_interaction()
    assert bot.strings_for(interaction) is LOCALES["silent"]
    assert bot.strings_for(interaction, private=True) is LOCALES["en"]


def test_unknown_locale_setting_falls_back_to_english() -> None:
    bot = BotApp(Config(discord_token="t", locale="xx"))
    assert bot.strings_for() is LOCALES["en"]
    assert bot.intents.members


def test_log_format_uses_single_spaces() -> None:
    formatter = LogFormatter()
    lines = [
        formatter.format(
            logging.LogRecord("bot", level, __file__, 1, "Hello.", None, None)
        )
        for level in (logging.INFO, logging.CRITICAL)
    ]
    assert lines[0].endswith("] [INFO] bot: Hello.")
    assert lines[1].endswith("] [CRITICAL] bot: Hello.")
