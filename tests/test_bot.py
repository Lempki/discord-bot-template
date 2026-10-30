"""Tests for bot.py that run without connecting to Discord."""

import contextvars
import inspect
import logging
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

from bot import BotApp, LogFormatter, ReconnectLogFilter
from config import Config
from localization import LOCALES
from tests.conftest import make_interaction, sent_messages
from utils.checks import NotInBotChannel
from utils.request_ids import current_request_id, start_request


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


@pytest.mark.parametrize(
    ("cogs", "members"),
    [
        (("help",), False),
        (("help", "voice", "media", "admin", "moderation"), False),
        (("help", "admin", "events"), True),
    ],
    ids=["default", "without-events", "with-events"],
)
def test_the_members_intent_is_asked_for_only_with_the_events_cog(
    cogs: tuple[str, ...], members: bool
) -> None:
    bot = BotApp(Config(discord_token="t", cogs_to_load=cogs))

    assert bot.intents.members is members


def test_the_bot_receives_no_direct_message_texts() -> None:
    bot = BotApp(Config(discord_token="t"))

    assert bot.intents.dm_messages is False
    # Mentions in servers still arrive, for the reply that opens the guide.
    assert bot.intents.guild_messages is True


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


def reconnect_record(error: BaseException) -> logging.LogRecord:
    """Builds the record that discord.py logs with logging.exception before a reconnect."""
    return logging.LogRecord(
        "discord.client",
        logging.ERROR,
        __file__,
        1,
        ReconnectLogFilter.RECONNECT_MESSAGE,
        (0.84,),
        (type(error), error, None),
    )


@pytest.mark.parametrize(
    ("error", "cause"),
    [
        (OSError("Name or service not known"), "OSError: Name or service not known"),
        (TimeoutError(), "TimeoutError"),
    ],
)
def test_lost_connection_logs_one_warning_line(
    error: BaseException, cause: str
) -> None:
    record = reconnect_record(error)

    assert ReconnectLogFilter().filter(record) is True

    line = LogFormatter().format(record)
    assert line.endswith(
        f"] [WARNING] discord.client: Lost the connection to Discord ({cause}). "
        "Reconnecting in 0.84 s."
    )
    assert "Traceback" not in line


def test_other_records_pass_unchanged() -> None:
    record = logging.LogRecord(
        "discord.client", logging.ERROR, __file__, 1, "Something else.", None, None
    )

    assert ReconnectLogFilter().filter(record) is True

    assert record.levelno == logging.ERROR
    assert record.getMessage() == "Something else."


def test_discord_still_logs_the_reconnect_message() -> None:
    # The filter matches discord.py's text, so rewording it would bring the traceback back.
    assert ReconnectLogFilter.RECONNECT_MESSAGE in inspect.getsource(
        discord.Client.connect
    )


async def test_stale_command_gets_a_clear_answer(bot: BotApp) -> None:
    interaction = make_interaction()

    await bot._on_command_error(interaction, app_commands.CommandNotFound("play", []))

    assert sent_messages(interaction) == [LOCALES["en"].command_unavailable]


def fake_guild(guild_id: int) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    return guild


async def test_cooldown_says_when_to_try_again(bot: BotApp) -> None:
    interaction = make_interaction()
    cooldown = app_commands.Cooldown(rate=1, per=10)

    await bot._on_command_error(
        interaction, app_commands.CommandOnCooldown(cooldown, retry_after=3.2)
    )

    # A cooldown is also a failed check, which must not read as the bot-channel message.
    assert sent_messages(interaction) == [LOCALES["en"].cooldown.format(seconds=4)]
    assert interaction.response.send_message.call_args.kwargs["ephemeral"] is True


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


@pytest.mark.parametrize(
    ("error", "text"),
    [
        (NotInBotChannel(), "bot_channel_only"),
        (app_commands.CheckFailure(), "command_not_allowed"),
    ],
)
async def test_a_failed_check_names_its_reason(
    error: app_commands.CheckFailure, text: str
) -> None:
    bot = BotApp(Config(discord_token="t", locale="en"))
    interaction = make_interaction()

    await bot._on_command_error(interaction, error)

    assert sent_messages(interaction) == [getattr(LOCALES["en"], text)]


def test_a_line_written_during_a_request_names_it() -> None:
    def format_line() -> str:
        start_request("1234567890")
        record = logging.LogRecord(
            "bot", logging.INFO, __file__, 1, "Hello.", None, None
        )
        return LogFormatter().format(record)

    line = contextvars.copy_context().run(format_line)

    assert line.endswith("] [INFO] bot: Hello. [request 1234567890]")


async def test_a_command_runs_under_its_interactions_id() -> None:
    bot = BotApp(Config(discord_token="t", locale="en"))
    interaction = make_interaction()
    interaction.id = 1234567890123456789

    assert await bot.tree.interaction_check(interaction) is True

    assert current_request_id() == "1234567890123456789"
