"""Tests for bot.py that run without connecting to Discord."""

import logging
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

from bot import BotApp, LogFormatter
from config import Config
from localization import LOCALES
from tests.conftest import make_interaction, sent_messages


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


async def test_stale_command_gets_a_clear_answer(bot: BotApp) -> None:
    interaction = make_interaction()

    await bot._on_command_error(interaction, app_commands.CommandNotFound("play", []))

    assert sent_messages(interaction) == [LOCALES["en"].command_unavailable]


def fake_guild(guild_id: int) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    return guild


async def test_leftover_guild_commands_are_removed(
    bot: BotApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_leftovers, clean = fake_guild(1), fake_guild(2)
    monkeypatch.setattr(BotApp, "guilds", property(lambda _: [with_leftovers, clean]))
    leftovers = {1: [MagicMock(name="play")], 2: []}
    monkeypatch.setattr(
        bot.tree,
        "fetch_commands",
        AsyncMock(side_effect=lambda guild: leftovers[guild.id]),
    )
    monkeypatch.setattr(bot.tree, "clear_commands", MagicMock())
    monkeypatch.setattr(bot.tree, "sync", AsyncMock())

    await bot.remove_guild_commands()

    bot.tree.clear_commands.assert_called_once_with(guild=with_leftovers)
    bot.tree.sync.assert_awaited_once_with(guild=with_leftovers)


async def test_a_guild_that_refuses_the_check_is_skipped(
    bot: BotApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(BotApp, "guilds", property(lambda _: [fake_guild(1)]))
    refused = discord.HTTPException(
        MagicMock(status=403, reason="Forbidden"), "Missing Access"
    )
    monkeypatch.setattr(bot.tree, "fetch_commands", AsyncMock(side_effect=refused))
    monkeypatch.setattr(bot.tree, "sync", AsyncMock())

    await bot.remove_guild_commands()

    bot.tree.sync.assert_not_awaited()


@pytest.mark.parametrize(("dev_guild_id", "expected_checks"), [(None, 1), (123, 0)])
async def test_guild_commands_are_checked_once_and_never_while_developing(
    monkeypatch: pytest.MonkeyPatch, dev_guild_id: int | None, expected_checks: int
) -> None:
    bot = BotApp(Config(discord_token="t", locale="en", dev_guild_id=dev_guild_id))
    check = AsyncMock()
    monkeypatch.setattr(bot, "remove_guild_commands", check)

    await bot.on_ready()
    await bot.on_ready()

    assert check.await_count == expected_checks
